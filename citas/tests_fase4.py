"""Pruebas de la Fase 4. El reloj se congela en fechas conocidas para probar las reglas exactas:
martes 3 de noviembre de 2026; el lunes 16 es festivo (Independencia de Cartagena)."""
from datetime import date, datetime, time
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from cuentas.auditoria import crear_fran
from cuentas.models import Vehiculo
from cuentas.pruebas_util import cliente_con_cuenta, usuario_con_rol

from . import servicios
from .models import Cita, TipoVisita

BOGOTA = ZoneInfo("America/Bogota")


def en(fecha, h, m=0):
    return datetime.combine(fecha, time(h, m), tzinfo=BOGOTA)


def reloj(fecha, h, m=0):
    """Congela 'ahora' en la fecha y hora indicadas (hora de Bogotá)."""
    return patch("django.utils.timezone.now", return_value=en(fecha, h, m))


MAR3, MIE4, SAB7, LUN16, LUN23, MAR24 = (date(2026, 11, 3), date(2026, 11, 4), date(2026, 11, 7),
                                         date(2026, 11, 16), date(2026, 11, 23), date(2026, 11, 24))


class Base(TestCase):
    def setUp(self):
        self.usuario_cliente, self.cliente = cliente_con_cuenta()
        self.usuario_otro, self.otro = cliente_con_cuenta("otro@correo.co", "Luis", "Pérez")
        self.otro.telefono = "3119876543"
        self.otro.save()
        self.empleado = usuario_con_rol("emp@t.co", "EMPLEADO")
        self.subjefe = usuario_con_rol("sub@t.co", "SUBJEFE")
        self.jefe = usuario_con_rol("jefe@t.co", "JEFE")
        self.fran = crear_fran("fran@t.co", "ClaveSegura-2026")
        self.aceite = TipoVisita.objects.get(nombre="Cambio de aceite")   # 45 min
        self.frenos = TipoVisita.objects.get(nombre="Frenos")             # 120 min
        self.carro = Vehiculo.objects.create(cliente=self.cliente, placa="ABC123", marca="Chevrolet",
                                             modelo="Spark", anio=2015)

    def agendar(self, inicio, usuario=None, cliente=None, tipo=None):
        return servicios.agendar(cliente or self.cliente, tipo or self.aceite, inicio,
                                 usuario or self.usuario_cliente, vehiculo=None)


class AlmuerzoYHorarioTests(Base):
    def test_ninguna_cita_cruza_el_almuerzo(self):
        with reloj(MAR3, 7):
            horas = [h.time() for h in servicios.franjas_libres(MIE4, self.aceite)]
            self.assertIn(time(12), horas)          # 12:00–12:45 ✔
            self.assertNotIn(time(12, 30), horas)   # 12:30–13:15 ✘
            self.assertNotIn(time(13), horas)
            self.assertNotIn(time(13, 30), horas)
            self.assertIn(time(14), horas)
            self.assertEqual((horas[0], horas[-1]), (time(8), time(17)))
            frenos = [h.time() for h in servicios.franjas_libres(MIE4, self.frenos)]
            self.assertIn(time(11), frenos)         # 11:00–13:00 termina justo al empezar el almuerzo
            self.assertNotIn(time(11, 30), frenos)
            with self.assertRaisesMessage(ValidationError, "almuerzo"):
                self.agendar(en(MIE4, 12, 30))

    def test_sabado_de_9_a_4_con_almuerzo(self):
        with reloj(MAR3, 7):
            horas = [h.time() for h in servicios.franjas_libres(SAB7, self.aceite)]
            self.assertEqual((horas[0], horas[-1]), (time(9), time(15)))
            self.assertNotIn(time(13), horas)


class VentanaTests(Base):
    def test_cliente_minimo_3_horas_personal_sin_minimo(self):
        with reloj(MIE4, 8):
            with self.assertRaisesMessage(ValidationError, "3 horas"):
                self.agendar(en(MIE4, 10, 30))
            self.agendar(en(MIE4, 11))
            servicios.agendar(self.otro, self.aceite, en(MIE4, 9), self.empleado)   # cliente que llegó al taller
            self.assertEqual(servicios.franjas_libres(MIE4, self.aceite)[0].time(), time(11))
            self.assertEqual(servicios.franjas_libres(MIE4, self.aceite, personal=True)[0].time(), time(8, 30))

    def test_maximo_20_dias_y_festivos(self):
        with reloj(MAR3, 7):
            dias = servicios.dias_para_calendario(self.aceite)
            self.assertEqual((dias[0]["fecha"], dias[-1]["fecha"]), (MAR3, LUN23))
            por_fecha = {d["fecha"]: d for d in dias}
            self.assertEqual(por_fecha[LUN16]["estado"], "cerrado")
            self.assertIn("Festivo", por_fecha[LUN16]["texto"])
            self.assertEqual(por_fecha[date(2026, 11, 8)]["estado"], "cerrado")   # domingo
            self.agendar(en(LUN23, 9))
            with self.assertRaisesMessage(ValidationError, "20 días"):
                self.agendar(en(MAR24, 9))

    def test_dia_lleno(self):
        with reloj(MAR3, 7):
            for _ in range(3):   # 3 bahías × todo el día con frenos de 2 h
                for h in (8, 10, 14, 16):
                    servicios.agendar(self.otro, self.frenos, en(MIE4, h), self.empleado)
                servicios.agendar(self.otro, self.aceite, en(MIE4, 12), self.empleado)
            estado = {d["fecha"]: d["estado"] for d in servicios.dias_para_calendario(self.aceite)}
            self.assertEqual(estado[MIE4], "lleno")


class ConfirmacionYAvisosTests(Base):
    def test_queda_confirmada_y_avisa_a_jefes_y_cliente(self):
        with reloj(MAR3, 7), self.captureOnCommitCallbacks(execute=True):
            cita = servicios.agendar(self.cliente, self.frenos, en(MIE4, 9), self.usuario_cliente,
                                     vehiculo=self.carro, nota="Chilla al frenar")
        self.assertEqual(cita.estado, Cita.CONFIRMADA)
        self.assertEqual(len(mail.outbox), 2)
        jefes, cliente = mail.outbox
        self.assertEqual(set(jefes.bcc), {"jefe@t.co", "fran@t.co"})   # ni empleado ni subjefe
        for dato in ("Ana Rojas", "3001234567", "wa.me/573001234567", "ABC123", "Chilla al frenar", "9:00 a. m."):
            self.assertIn(dato, jefes.body)
        self.assertEqual(cliente.to, ["cliente@correo.co"])
        self.assertIn("confirmada", cliente.body)

    def test_limite_de_citas_activas_por_cliente(self):
        with reloj(MAR3, 7):
            for h in (8, 9, 10):
                self.agendar(en(MIE4, h))
            with self.assertRaisesMessage(ValidationError, "3 citas próximas"):
                self.agendar(en(MIE4, 11))
            servicios.agendar(self.cliente, self.aceite, en(MIE4, 11), self.empleado)   # el taller sí puede

    def test_recordatorio_una_sola_vez(self):
        with reloj(MAR3, 7):
            self.agendar(en(MIE4, 9))
        mail.outbox.clear()
        with reloj(MAR3, 17):
            call_command("recordar_citas", stdout=StringIO())
            call_command("recordar_citas", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Recordatorio", mail.outbox[0].subject)


class CancelarYCambiarTests(Base):
    def setUp(self):
        super().setUp()
        with reloj(MAR3, 7):
            self.cita = self.agendar(en(MIE4, 14))

    def test_cliente_cancela_hasta_4_horas_antes(self):
        with reloj(MIE4, 10, 1):
            with self.assertRaisesMessage(ValidationError, "4 horas"):
                servicios.cancelar(self.cita.pk, self.usuario_cliente)
        with reloj(MIE4, 10), self.captureOnCommitCallbacks(execute=True):
            servicios.cancelar(self.cita.pk, self.usuario_cliente)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, Cita.CANCELADA)
        self.assertEqual([m.to for m in mail.outbox][-1], [settings.DEFAULT_FROM_EMAIL])  # solo a los jefes (copia oculta)

    def test_taller_cancela_cuando_sea_con_motivo_y_avisa_al_cliente(self):
        with reloj(MIE4, 13):
            with self.assertRaisesMessage(ValidationError, "motivo"):
                servicios.cancelar(self.cita.pk, self.empleado, "")
            with self.captureOnCommitCallbacks(execute=True):
                servicios.cancelar(self.cita.pk, self.empleado, "Se dañó el elevador")
        self.assertTrue(any(m.to == ["cliente@correo.co"] and "elevador" in m.body for m in mail.outbox))

    def test_otro_cliente_no_puede(self):
        with reloj(MAR3, 8), self.assertRaises(PermissionDenied):
            servicios.cancelar(self.cita.pk, self.usuario_otro)

    def test_reprogramar(self):
        with reloj(MAR3, 8), self.captureOnCommitCallbacks(execute=True):
            servicios.reprogramar(self.cita.pk, self.usuario_cliente, en(SAB7, 10))
        self.cita.refresh_from_db()
        self.assertEqual((self.cita.inicio, self.cita.veces_reprogramada), (en(SAB7, 10), 1))
        self.assertTrue(any("reprogramada" in m.subject.lower() for m in mail.outbox))
        with reloj(SAB7, 6, 30), self.assertRaisesMessage(ValidationError, "4 horas"):
            servicios.reprogramar(self.cita.pk, self.usuario_cliente, en(LUN23, 9))

    def test_reprogramar_a_hora_llena_no_cambia_nada(self):
        with reloj(MAR3, 8):
            for _ in range(3):
                servicios.agendar(self.otro, self.aceite, en(SAB7, 10), self.empleado)
            with self.assertRaises(ValidationError):
                servicios.reprogramar(self.cita.pk, self.usuario_cliente, en(SAB7, 10))
        self.cita.refresh_from_db()
        self.assertEqual((self.cita.inicio, self.cita.veces_reprogramada), (en(MIE4, 14), 0))

    def test_marcar_atendida_solo_el_dia(self):
        with reloj(MAR3, 8), self.assertRaises(ValidationError):
            servicios.marcar(self.cita.pk, self.empleado, Cita.ATENDIDA)
        with reloj(MIE4, 15):
            servicios.marcar(self.cita.pk, self.empleado, Cita.ATENDIDA)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, Cita.ATENDIDA)


class BloqueosTests(Base):
    def test_cerrar_dia_y_bloquear_horas(self):
        with reloj(MAR3, 7):
            cita = self.agendar(en(MIE4, 9))
            _, afectadas = servicios.bloquear(self.subjefe, MIE4, "Inventario anual")
            self.assertEqual(afectadas, [cita])                      # se avisa, no se cancela sola
            estado = {d["fecha"]: d for d in servicios.dias_para_calendario(self.aceite)}
            self.assertEqual(estado[MIE4]["estado"], "cerrado")
            servicios.bloquear(self.jefe, SAB7, "Capacitación", time(9), time(12))
            self.assertEqual(servicios.franjas_libres(SAB7, self.aceite)[0].time(), time(12))
            with self.assertRaises(PermissionDenied):
                servicios.bloquear(self.empleado, SAB7, "x")


class PantallasTests(Base):
    def test_cliente_agenda_con_vehiculo_nuevo(self):
        self.client.force_login(self.usuario_otro)
        with reloj(MAR3, 7):
            r = self.client.get(reverse("citas:agendar"), {"tipo": self.aceite.pk, "fecha": "2026-11-04"})
            self.assertContains(r, "12:00 p. m.")
            self.assertNotContains(r, "1:00 p. m.</span>")
            r = self.client.post(reverse("citas:agendar"), {
                "tipo": self.aceite.pk, "fecha": "2026-11-04", "hora": "09:00",
                "placa": "xyz-12a", "marca": "Yamaha", "modelo": "FZ", "anio": "2022", "nota": "Revisar aceite"})
        self.assertRedirects(r, reverse("citas:mis_citas"))
        cita = Cita.objects.get(cliente=self.otro)
        self.assertEqual(cita.vehiculo.placa, "XYZ12A")

    def test_placa_de_otro_cliente_no_crea_nada(self):
        self.client.force_login(self.usuario_otro)
        with reloj(MAR3, 7):
            r = self.client.post(reverse("citas:agendar"), {
                "tipo": self.aceite.pk, "fecha": "2026-11-04", "hora": "09:00",
                "placa": "ABC123", "marca": "X", "modelo": "Y", "anio": "2020"})
        self.assertContains(r, "registrada con otro cliente")
        self.assertFalse(Cita.objects.exists())

    def test_fragmento_htmx_de_horas(self):
        self.client.force_login(self.usuario_cliente)
        with reloj(MAR3, 7):
            r = self.client.get(reverse("citas:horas"), {"tipo": self.aceite.pk, "fecha": "2026-11-16"})
        self.assertNotContains(r, "<html")
        self.assertContains(r, "no atiende")

    def test_cita_ajena_da_404(self):
        with reloj(MAR3, 7):
            cita = self.agendar(en(MIE4, 9))
        self.client.force_login(self.usuario_otro)
        self.assertEqual(self.client.get(reverse("citas:reprogramar", args=[cita.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("citas:cancelar", args=[cita.pk])).status_code, 404)

    def test_agenda_solo_para_personal_y_muestra_contacto(self):
        with reloj(MAR3, 7):
            self.agendar(en(MIE4, 9))
        self.client.force_login(self.usuario_cliente)
        self.assertEqual(self.client.get(reverse("citas:agenda")).status_code, 403)
        self.client.force_login(self.empleado)
        r = self.client.get(reverse("citas:agenda"), {"fecha": "2026-11-04"})
        self.assertContains(r, "Ana Rojas")
        self.assertContains(r, "wa.me/573001234567")
        self.assertNotContains(r, "Bloquear días u horas")   # el empleado no bloquea

    def test_personal_agenda_para_cliente_por_celular(self):
        self.client.force_login(self.empleado)
        with reloj(MIE4, 8):
            r = self.client.post(reverse("citas:agendar"), {
                "tipo": self.aceite.pk, "fecha": "2026-11-04", "hora": "09:00", "cliente": "300 123 4567",
                "placa": "ABC123", "marca": "Chevrolet", "modelo": "Spark", "anio": "2015"})
        self.assertRedirects(r, reverse("citas:agenda") + "?fecha=2026-11-04")
        self.assertEqual(Cita.objects.get().vehiculo, self.carro)
