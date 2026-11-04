from datetime import date
from decimal import Decimal

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from pedidos.models import Pedido

from .auditoria import auditoria_para, crear_fran, registrar
from .models import Auditoria, AuditoriaFran, Cliente, Usuario
from .permisos import tiene_permiso
from .pruebas_util import cliente_con_cuenta, usuario_con_rol
from .validadores import calcular_edad


SISTEMA = settings.TALLER["EMAIL_SISTEMA"]   # usuario técnico creado por migración


class FranTests(TestCase):
    def setUp(self):
        self.fran = crear_fran("fran@taller.co", "ClaveSegura-2026")
        self.jefe = usuario_con_rol("jefe@taller.co", "JEFE")

    def test_solo_puede_existir_un_fran(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_fran("otro@taller.co", "ClaveSegura-2026")

    def test_fran_no_aparece_en_consultas_normales(self):
        self.assertNotIn(self.fran, Usuario.objects.all())
        self.assertEqual(Usuario.objects.exclude(email=SISTEMA).count(), 1)   # solo el jefe
        self.assertIn(self.fran, Usuario.todos.all())

    def test_fran_si_puede_iniciar_sesion(self):
        self.assertEqual(authenticate(username="fran@taller.co", password="ClaveSegura-2026"), self.fran)
        self.assertTrue(self.client.login(username="fran@taller.co", password="ClaveSegura-2026"))

    def test_en_historiales_aparece_como_gerencia(self):
        self.assertEqual(self.fran.nombre_visible, "Gerencia")

    def test_auditoria_separada_y_vista_total(self):
        registrar(self.jefe, "editar_precio", "Producto", 1)
        registrar(self.fran, "anular_descuento", "Pedido", 9)
        self.assertEqual(Auditoria.objects.count(), 1)
        self.assertEqual(AuditoriaFran.objects.count(), 1)
        self.assertEqual([r.accion for r in auditoria_para(self.jefe)], ["editar_precio"])
        self.assertEqual({r.accion for r in auditoria_para(self.fran)}, {"editar_precio", "anular_descuento"})

    def test_auditoria_inmutable_en_la_base_de_datos(self):
        registrar(self.jefe, "x", "Producto", 1)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Auditoria.objects.update(accion="borrado")   # salta el save() del modelo; lo frena el trigger
        with self.assertRaises(DatabaseError), transaction.atomic():
            Auditoria.objects.all()._raw_delete(Auditoria.objects.db)


class PermisosTests(TestCase):
    def test_matriz(self):
        empleado = usuario_con_rol("e@t.co", "EMPLEADO")
        subjefe = usuario_con_rol("s@t.co", "SUBJEFE")
        jefe = usuario_con_rol("j@t.co", "JEFE")
        ingeniero = usuario_con_rol("i@t.co", "INGENIERO")
        fran = crear_fran("f@t.co", "ClaveSegura-2026")

        self.assertFalse(tiene_permiso(empleado, "apartados.aprobar"))
        self.assertTrue(tiene_permiso(subjefe, "apartados.aprobar"))
        self.assertFalse(tiene_permiso(subjefe, "contabilidad.ver"))
        self.assertTrue(tiene_permiso(jefe, "contabilidad.ver"))
        self.assertFalse(tiene_permiso(jefe, "auditoria.ver_total"))
        self.assertTrue(tiene_permiso(ingeniero, "sistema.mantenimiento"))
        self.assertFalse(tiene_permiso(ingeniero, "contabilidad.ver"))
        self.assertFalse(tiene_permiso(ingeniero, "clientes.ver_basico"))
        self.assertTrue(tiene_permiso(fran, "auditoria.ver_total"))
        self.assertTrue(tiene_permiso(fran, "contabilidad.ver"))

    def test_bloqueado_no_entra_ni_conserva_permisos(self):
        jefe = usuario_con_rol("j@t.co", "JEFE")
        jefe.bloqueado = True
        jefe.save()
        self.assertIsNone(authenticate(username="j@t.co", password="ClaveSegura-2026"))
        self.assertFalse(tiene_permiso(jefe, "contabilidad.ver"))


class MayoriaDeEdadTests(TestCase):
    def _cliente(self, nacimiento):
        return Cliente(nombres="X", apellidos="Y", telefono="3001234567", fecha_nacimiento=nacimiento,
                       acepta_datos_en=timezone.now(), version_politica="v1")

    def test_menor_rechazado_y_mayor_aceptado(self):
        hoy = timezone.localdate()
        cumple_18_manana = date(hoy.year - 18, hoy.month, hoy.day) + timezone.timedelta(days=1)
        cumple_18_hoy = date(hoy.year - 18, hoy.month, hoy.day)
        with self.assertRaises(ValidationError):
            self._cliente(cumple_18_manana).full_clean()
        self._cliente(cumple_18_hoy).full_clean()   # no lanza error

    def test_calculo_de_edad(self):
        self.assertEqual(calcular_edad(date(2008, 11, 2), date(2026, 11, 1)), 17)
        self.assertEqual(calcular_edad(date(2008, 11, 1), date(2026, 11, 1)), 18)


class AnonimizarTests(TestCase):
    def test_conserva_ventas_y_borra_datos_personales(self):
        usuario, cliente = cliente_con_cuenta()
        pedido = Pedido.objects.create(
            cliente=cliente, modalidad=Pedido.RECOGER, metodo_pago=Pedido.EN_TIENDA,
            telefono_contacto="3001234567", subtotal=Decimal("50000"), total=Decimal("50000"),
        )
        cliente.anonimizar()
        pedido.refresh_from_db()
        cliente.refresh_from_db()
        usuario.refresh_from_db()
        self.assertEqual(pedido.total, Decimal("50000"))
        self.assertEqual(cliente.nombres, "Cliente")
        self.assertFalse(usuario.puede_entrar)
        self.assertNotIn("correo.co", usuario.email)
