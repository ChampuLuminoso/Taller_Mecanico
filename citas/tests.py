from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from cuentas.pruebas_util import cliente_con_cuenta, usuario_con_rol

from . import calendario, servicios
from .models import Bahia, BloqueoAgenda, Cita, ExcepcionCalendario, TipoVisita


def proximo_martes_laboral():
    d = timezone.localdate() + timedelta(days=7)
    while d.weekday() != 1 or not calendario.es_laboral(d):
        d += timedelta(days=1)
    return d


def a_las(fecha, hora, minuto=0):
    return timezone.make_aware(datetime.combine(fecha, time(hora, minuto)))


class CalendarioTests(TestCase):
    def test_festivos_colombianos_2026(self):
        self.assertIn("Todos los Santos", calendario.nombre_festivo(date(2026, 11, 2)))  # lunes, Ley Emiliani
        self.assertFalse(calendario.es_laboral(date(2026, 12, 25)))
        self.assertFalse(calendario.es_laboral(date(2026, 11, 16)))   # Independencia de Cartagena
        self.assertFalse(calendario.es_laboral(date(2026, 7, 13)))    # Virgen de Chiquinquirá (Ley 2578/2026)

    def test_domingo_cerrado_sabado_medio_dia(self):
        self.assertFalse(calendario.es_laboral(date(2026, 11, 8)))    # domingo
        sabado = calendario.info_dia(date(2026, 11, 7))
        self.assertEqual((sabado.tipo, sabado.cierra), (calendario.LABORAL, time(16)))

    def test_excepciones_del_taller_mandan(self):
        jefe = usuario_con_rol("j@t.co", "JEFE")
        ExcepcionCalendario.objects.create(fecha=date(2026, 11, 4), tipo="CERRADO",
                                           motivo="Inventario anual", creado_por=jefe)
        ExcepcionCalendario.objects.create(fecha=date(2026, 12, 8), tipo="ABIERTO",
                                           motivo="Temporada alta", creado_por=jefe)
        self.assertFalse(calendario.es_laboral(date(2026, 11, 4)))
        self.assertTrue(calendario.es_laboral(date(2026, 12, 8)))


class AgendaTests(TestCase):
    def setUp(self):
        self.usuario_cliente, self.cliente = cliente_con_cuenta()
        self.empleado = usuario_con_rol("e@t.co", "EMPLEADO")
        self.jefe = usuario_con_rol("j@t.co", "JEFE")
        self.aceite = TipoVisita.objects.get(nombre="Cambio de aceite")
        self.dia = proximo_martes_laboral()

    def test_capacidad_de_tres_vehiculos(self):
        inicio = a_las(self.dia, 9)
        bahias = {servicios.agendar(self.cliente, self.aceite, inicio, self.empleado).bahia_id for _ in range(3)}
        self.assertEqual(len(bahias), 3)
        with self.assertRaises(ValidationError):
            servicios.agendar(self.cliente, self.aceite, inicio, self.empleado)

    def test_cancelar_libera_el_cupo(self):
        inicio = a_las(self.dia, 9)
        citas = [servicios.agendar(self.cliente, self.aceite, inicio, self.empleado) for _ in range(3)]
        citas[0].estado = Cita.CANCELADA
        citas[0].save()
        servicios.agendar(self.cliente, self.aceite, inicio, self.empleado)   # ya cabe

    def test_la_base_de_datos_impide_el_cruce(self):
        bahia = Bahia.objects.first()
        Cita.objects.create(cliente=self.cliente, tipo_visita=self.aceite, bahia=bahia,
                            inicio=a_las(self.dia, 9), fin=a_las(self.dia, 10))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cita.objects.create(cliente=self.cliente, tipo_visita=self.aceite, bahia=bahia,
                                inicio=a_las(self.dia, 9, 30), fin=a_las(self.dia, 10, 30))
        # Citas pegadas (9–10 y 10–11) sí se permiten.
        Cita.objects.create(cliente=self.cliente, tipo_visita=self.aceite, bahia=bahia,
                            inicio=a_las(self.dia, 10), fin=a_las(self.dia, 11))

    def test_fuera_de_horario_festivo_o_pasado(self):
        with self.assertRaises(ValidationError):
            servicios.agendar(self.cliente, self.aceite, a_las(self.dia, 17, 30), self.empleado)  # termina 18:15
        with self.assertRaises(ValidationError):
            servicios.agendar(self.cliente, self.aceite, a_las(date(2026, 12, 25), 9), self.empleado)
        with self.assertRaises(ValidationError):
            servicios.agendar(self.cliente, self.aceite, timezone.now() - timedelta(days=1), self.empleado)

    def test_bloqueo_total_de_horas(self):
        BloqueoAgenda.objects.create(inicio=a_las(self.dia, 14), fin=a_las(self.dia, 16),
                                     motivo="Capacitación", creado_por=self.jefe)
        with self.assertRaises(ValidationError):
            servicios.agendar(self.cliente, self.aceite, a_las(self.dia, 14, 30), self.empleado)
        self.assertNotIn(a_las(self.dia, 14, 30), servicios.franjas_libres(self.dia, self.aceite))

    def test_cliente_agenda_para_si_mismo_pero_no_para_otros(self):
        servicios.agendar(self.cliente, self.aceite, a_las(self.dia, 8), self.usuario_cliente)
        _, otro = cliente_con_cuenta("otro@correo.co", "Luis", "Pérez")
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            servicios.agendar(otro, self.aceite, a_las(self.dia, 8), self.usuario_cliente)

    def test_franjas_libres(self):
        franjas = servicios.franjas_libres(self.dia, self.aceite)
        self.assertEqual(franjas[0].time(), time(8))
        self.assertEqual(franjas[-1].time(), time(17))   # 17:00 + 45 min = 17:45 < 18:00
