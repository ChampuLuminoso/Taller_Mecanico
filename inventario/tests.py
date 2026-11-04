from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.utils import timezone

from cuentas.pruebas_util import cliente_con_cuenta, usuario_con_rol

from . import servicios as s
from .models import Apartado, MovimientoInventario, Producto


class InventarioTests(TestCase):
    def setUp(self):
        self.empleado = usuario_con_rol("e@t.co", "EMPLEADO")
        self.subjefe = usuario_con_rol("s@t.co", "SUBJEFE")
        self.jefe = usuario_con_rol("j@t.co", "JEFE")
        self.usuario_cliente, self.cliente = cliente_con_cuenta()
        self.p = Producto.objects.create(sku="pf-001", nombre="Pastillas de freno delanteras",
                                         precio_venta=Decimal("85000"))

    def test_sku_se_normaliza_y_arranca_no_disponible(self):
        self.assertEqual(self.p.sku, "PF-001")
        self.assertEqual(self.p.disponibilidad, "No disponible")

    def test_entrada_actualiza_stock_e_historial(self):
        s.registrar_entrada(self.p.pk, 5, self.jefe, "Compra a proveedor")
        p = Producto.objects.con_disponibilidad().get(pk=self.p.pk)
        self.assertEqual((p.cantidad_fisica, p.unidades_disponibles, p.estado_disponibilidad), (5, 5, "Disponible"))
        mov = MovimientoInventario.objects.get()
        self.assertEqual((mov.delta_fisica, mov.saldo_fisica, mov.usuario), (5, 5, self.jefe))

    def test_no_se_vende_lo_que_no_hay(self):
        s.registrar_entrada(self.p.pk, 1, self.jefe, "Compra")
        with self.assertRaises(ValidationError):
            s.mover(self.p.pk, MovimientoInventario.VENTA, 2, self.empleado, "Venta")
        self.p.refresh_from_db()
        self.assertEqual(self.p.cantidad_fisica, 1)

    def test_movimiento_sin_motivo_rechazado(self):
        with self.assertRaises(ValidationError):
            s.mover(self.p.pk, MovimientoInventario.ENTRADA, 1, self.empleado, "  ")

    def test_flujo_solicitud_aprobacion_y_entrega(self):
        s.registrar_entrada(self.p.pk, 2, self.jefe, "Compra")
        sol = s.solicitar_apartado(self.cliente, self.p, 1, "Lo recojo el viernes", self.usuario_cliente)
        self.p.refresh_from_db()
        self.assertEqual(self.p.disponible, 2)            # pedir no descuenta

        with self.assertRaises(PermissionDenied):         # un empleado no decide
            s.responder_solicitud(sol.pk, self.empleado, aprobar=True)
        with self.assertRaises(PermissionDenied):         # el cliente tampoco
            s.responder_solicitud(sol.pk, self.usuario_cliente, aprobar=True)

        apartado = s.responder_solicitud(sol.pk, self.subjefe, aprobar=True, respuesta="Listo")
        self.p.refresh_from_db()
        self.assertEqual((self.p.cantidad_fisica, self.p.cantidad_apartada, self.p.disponible), (2, 1, 1))
        self.assertGreater(apartado.vence_en, timezone.now())

        s.cerrar_apartado(apartado.pk, self.empleado, Apartado.ENTREGADO)
        self.p.refresh_from_db()
        self.assertEqual((self.p.cantidad_fisica, self.p.cantidad_apartada), (1, 0))

    def test_no_se_aparta_mas_de_lo_disponible(self):
        s.registrar_entrada(self.p.pk, 1, self.jefe, "Compra")
        sol = s.solicitar_apartado(self.cliente, self.p, 2, "", self.usuario_cliente)
        with self.assertRaises(ValidationError):
            s.responder_solicitud(sol.pk, self.subjefe, aprobar=True)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, "PENDIENTE")   # todo se deshizo

    def test_vencimiento_devuelve_al_stock(self):
        s.registrar_entrada(self.p.pk, 3, self.jefe, "Compra")
        a = s.crear_apartado(self.p, self.cliente, 2, self.subjefe)
        cerrados = s.vencer_apartados(self.subjefe, ahora=a.vence_en + timedelta(minutes=1))
        self.assertEqual(cerrados, 1)
        self.p.refresh_from_db()
        a.refresh_from_db()
        self.assertEqual((a.estado, self.p.disponible), ("VENCIDO", 3))

    def test_abono_da_mas_plazo(self):
        s.registrar_entrada(self.p.pk, 2, self.jefe, "Compra")
        sin = s.crear_apartado(self.p, self.cliente, 1, self.subjefe)
        con = s.crear_apartado(self.p, self.cliente, 1, self.subjefe, abono=Decimal("20000"))
        self.assertGreater(con.vence_en, sin.vence_en)

    def test_historial_inmutable(self):
        s.registrar_entrada(self.p.pk, 1, self.jefe, "Compra")
        with self.assertRaises(DatabaseError), transaction.atomic():
            MovimientoInventario.objects.update(delta_fisica=100)
