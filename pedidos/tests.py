"""Pruebas de la Fase 5: tienda pública, carrito, pedidos y su ciclo de vida."""
from decimal import Decimal

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from cuentas.auditoria import crear_fran
from cuentas.models import Direccion
from cuentas.pruebas_util import cliente_con_cuenta, usuario_con_rol
from inventario import servicios as inv
from inventario.models import Categoria, MovimientoInventario as M, Producto, SolicitudApartado

from . import servicios as s
from .models import Pedido

P = Pedido


class Base(TestCase):
    def setUp(self):
        self.empleado = usuario_con_rol("emp@t.co", "EMPLEADO")
        self.subjefe = usuario_con_rol("sub@t.co", "SUBJEFE")
        self.jefe = usuario_con_rol("jefe@t.co", "JEFE")
        self.fran = crear_fran("fran@t.co", "ClaveSegura-2026")
        self.u, self.cliente = cliente_con_cuenta()
        self.u2, self.otro = cliente_con_cuenta("otro@correo.co", "Luis", "Pérez")
        frenos = Categoria.objects.get(nombre="Frenos")
        self.pastillas = Producto.objects.create(sku="FRE-001", nombre="Pastillas de freno", categoria=frenos,
                                                 precio_venta=Decimal("85000"), stock_minimo=1)
        self.pastillas.compatibilidades.create(marca_vehiculo="Chevrolet", modelo="Spark", anio_desde=2010, anio_hasta=2018)
        self.aceite = Producto.objects.create(sku="ACE-001", nombre="Aceite 20W50", precio_venta=Decimal("48000"))
        self.oculto = Producto.objects.create(sku="OCU-001", nombre="Producto desactivado", precio_venta=1, activo=False)
        inv.registrar_entrada(self.pastillas.pk, 5, self.jefe, "Compra")
        inv.registrar_entrada(self.aceite.pk, 2, self.jefe, "Compra")
        self.casa = Direccion.objects.create(cliente=self.cliente, localidad="Suba", barrio="Niza",
                                             direccion="Calle 127 # 58-20", principal=True)

    def pedido(self, lineas=None, modalidad=P.ENVIO, metodo=P.CONTRA_ENTREGA, usuario=None, cliente=None):
        return s.crear_pedido(usuario or self.u, cliente or self.cliente,
                              lineas or [(self.pastillas.pk, 2), (self.aceite.pk, 1)],
                              modalidad=modalidad, metodo_pago=metodo, telefono="3001234567",
                              direccion=self.casa if modalidad == P.ENVIO else None)

    def stock(self, producto):
        producto.refresh_from_db()
        return producto.cantidad_fisica


class TiendaPublicaTests(Base):
    def test_sin_cuenta_se_ve_precio_y_stock(self):
        r = self.client.get(reverse("tienda:catalogo"))
        self.assertContains(r, "Pastillas de freno")
        self.assertContains(r, "$85.000")
        self.assertContains(r, "5 disponibles")
        self.assertNotContains(r, "Producto desactivado")
        self.assertEqual(self.client.get(reverse("tienda:producto", args=["OCU-001"])).status_code, 404)

    def test_busqueda_por_carro_y_anio(self):
        r = self.client.get(reverse("tienda:catalogo"), {"q": "spark 2015"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "<html")
        self.assertContains(r, "Pastillas de freno")
        self.assertNotContains(r, "Aceite")
        r = self.client.get(reverse("tienda:catalogo"), {"q": "spark 2020"})
        self.assertNotContains(r, "Pastillas de freno")   # fuera del rango de años

    def test_vista_rapida_es_fragmento(self):
        r = self.client.get(reverse("tienda:producto", args=["FRE-001"]), HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "<html")
        self.assertContains(r, "Chevrolet Spark 2010–2018")

    def test_carrito_sin_cuenta_y_registro_al_comprar(self):
        self.client.post(reverse("tienda:agregar", args=[self.pastillas.pk]), {"cantidad": 9})
        r = self.client.get(reverse("tienda:carrito"))
        self.assertContains(r, 'value="5"')                     # no deja más de lo disponible
        r = self.client.get(reverse("tienda:comprar"))
        self.assertRedirects(r, reverse("cuentas:registro") + "?next=" + reverse("tienda:comprar"))

    def test_carrito_sobrevive_al_iniciar_sesion(self):
        self.client.post(reverse("tienda:agregar", args=[self.aceite.pk]))
        self.client.post(reverse("cuentas:login") + "?next=/comprar/",
                         {"email": "cliente@correo.co", "password": "ClaveSegura-2026", "next": "/comprar/"})
        r = self.client.get(reverse("tienda:comprar"))
        self.assertContains(r, "Aceite 20W50")
        self.assertContains(r, "$2.000")


class PedidoTests(Base):
    def test_crear_no_descuenta_y_cobra_envio_fijo(self):
        with self.captureOnCommitCallbacks(execute=True):
            p = self.pedido()
        self.assertEqual((p.estado, p.subtotal, p.costo_envio, p.total),
                         (P.RECIBIDO, Decimal("218000"), Decimal("2000"), Decimal("220000")))
        self.assertEqual(self.stock(self.pastillas), 5)          # aún no se descuenta
        self.assertIn("Suba", p.direccion_texto)
        taller, cliente = mail.outbox
        self.assertEqual(set(taller.bcc), {"sub@t.co", "jefe@t.co", "fran@t.co"})
        self.assertIn("wa.me/573001234567", taller.body)
        self.assertEqual(cliente.to, ["cliente@correo.co"])

    def test_recoger_en_taller_es_gratis(self):
        p = self.pedido(modalidad=P.RECOGER, metodo=P.EN_TIENDA)
        self.assertEqual((p.costo_envio, p.total, p.direccion_texto), (0, Decimal("218000"), ""))

    def test_reglas_al_crear(self):
        with self.assertRaisesMessage(ValidationError, "solo hay 2"):
            self.pedido([(self.aceite.pk, 3)])
        with self.assertRaisesMessage(ValidationError, "contra entrega"):
            self.pedido(metodo=P.EN_TIENDA)
        with self.assertRaises(ValidationError):
            self.pedido([(self.oculto.pk, 1)])
        with self.assertRaises(PermissionDenied):
            self.pedido(usuario=self.u, cliente=self.otro)       # a nombre de otro
        with self.assertRaises(PermissionDenied):
            self.pedido(usuario=self.empleado)

    def test_precio_queda_congelado(self):
        p = self.pedido()
        self.pastillas.precio_venta = Decimal("99000")
        self.pastillas.save()
        self.assertEqual(p.items.get(sku="FRE-001").precio_unitario, Decimal("85000"))


class CicloTests(Base):
    def test_solo_subjefe_y_jefe_confirman_y_ahi_se_descuenta(self):
        p = self.pedido()
        with self.assertRaises(PermissionDenied):
            s.confirmar(p.pk, self.empleado)
        with self.captureOnCommitCallbacks(execute=True):
            s.confirmar(p.pk, self.subjefe)
        self.assertEqual((self.stock(self.pastillas), self.stock(self.aceite)), (3, 1))
        mov = self.pastillas.movimientos.filter(tipo=M.VENTA).get()
        self.assertEqual((mov.referencia, mov.usuario), (f"pedido:{p.pk}", self.subjefe))
        self.assertTrue(any("confirmado" in m.subject.lower() for m in mail.outbox))

    def test_confirmar_es_todo_o_nada(self):
        p1 = self.pedido([(self.aceite.pk, 2)])
        p2 = self.pedido([(self.pastillas.pk, 1), (self.aceite.pk, 2)], cliente=self.otro, usuario=self.u2,
                         modalidad=P.RECOGER, metodo=P.EN_TIENDA)
        s.confirmar(p1.pk, self.jefe)                             # se lleva todo el aceite
        with self.assertRaisesMessage(ValidationError, "ACE-001"):
            s.confirmar(p2.pk, self.jefe)
        p2.refresh_from_db()
        self.assertEqual((p2.estado, self.stock(self.pastillas)), (P.RECIBIDO, 5))   # ni las pastillas

    def test_envio_completo_y_cobro(self):
        p = self.pedido()
        s.confirmar(p.pk, self.jefe)
        s.avanzar(p.pk, self.empleado, P.ALISTADO)
        with self.assertRaises(ValidationError):
            s.avanzar(p.pk, self.empleado, P.ENTREGADO)          # a domicilio primero sale a entrega
        s.avanzar(p.pk, self.empleado, P.EN_CAMINO)
        s.avanzar(p.pk, self.empleado, P.ENTREGADO)
        p.refresh_from_db()
        self.assertEqual(p.estado, P.ENTREGADO)
        self.assertTrue(p.pagado and p.entregado_en)

    def test_recoger_no_sale_a_domicilio(self):
        p = self.pedido(modalidad=P.RECOGER, metodo=P.EN_TIENDA)
        s.confirmar(p.pk, self.jefe)
        with self.assertRaises(ValidationError):
            s.avanzar(p.pk, self.empleado, P.EN_CAMINO)
        s.avanzar(p.pk, self.empleado, P.ENTREGADO)

    def test_cancelaciones(self):
        p = self.pedido()
        with self.assertRaises(PermissionDenied):
            s.cancelar(p.pk, self.u2)                             # otro cliente
        s.cancelar(p.pk, self.u)                                  # el dueño, antes de confirmar
        p2 = self.pedido()
        s.confirmar(p2.pk, self.jefe)
        with self.assertRaisesMessage(ValidationError, "WhatsApp"):
            s.cancelar(p2.pk, self.u)                             # ya confirmado: solo el taller
        with self.assertRaises(PermissionDenied):
            s.cancelar(p2.pk, self.empleado, "x")
        with self.captureOnCommitCallbacks(execute=True):
            s.cancelar(p2.pk, self.subjefe, "El cliente no contestó")
        self.assertEqual(self.stock(self.pastillas), 5)           # volvió al inventario
        self.assertTrue(any("no contestó" in m.body for m in mail.outbox))


class PantallasTests(Base):
    def test_compra_completa_con_direccion_nueva(self):
        self.client.force_login(self.u2)
        self.client.post(reverse("tienda:agregar", args=[self.pastillas.pk]), {"cantidad": 2})
        r = self.client.post(reverse("tienda:comprar"), {
            "modalidad": "ENVIO", "metodo_pago": "EN_TIENDA", "telefono": "3119876543",
            "localidad": "Kennedy", "barrio": "Castilla", "direccion_texto": "Cra 78 # 8-15"})
        self.assertRedirects(r, reverse("pedidos:mis_pedidos"))
        p = Pedido.objects.get(cliente=self.otro)
        self.assertEqual((p.metodo_pago, p.total), (P.CONTRA_ENTREGA, Decimal("172000")))
        self.assertTrue(self.otro.direcciones.filter(barrio="Castilla", principal=True).exists())
        self.assertEqual(self.client.get(reverse("tienda:carrito")).context["lineas"], [])

    def test_envio_sin_direccion_no_crea_nada(self):
        self.client.force_login(self.u2)
        self.client.post(reverse("tienda:agregar", args=[self.aceite.pk]))
        r = self.client.post(reverse("tienda:comprar"), {"modalidad": "ENVIO", "metodo_pago": "CONTRA_ENTREGA",
                                                         "telefono": "3119876543"})
        self.assertContains(r, "Necesitamos este dato")
        self.assertFalse(Pedido.objects.exists())

    def test_panel_pedidos_por_rol(self):
        p = self.pedido()
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse("pedidos:lista")).status_code, 403)
        self.client.force_login(self.empleado)
        r = self.client.get(reverse("pedidos:detalle_taller", args=[p.pk]))
        self.assertNotContains(r, "Confirmar y descontar")
        self.client.post(reverse("pedidos:accion", args=[p.pk]), {"accion": "confirmar"})
        p.refresh_from_db()
        self.assertEqual(p.estado, P.RECIBIDO)
        self.client.force_login(self.subjefe)
        self.assertContains(self.client.get(reverse("pedidos:detalle_taller", args=[p.pk])), "Confirmar y descontar")
        self.client.post(reverse("pedidos:accion", args=[p.pk]), {"accion": "confirmar"})
        p.refresh_from_db()
        self.assertEqual(p.estado, P.CONFIRMADO)

    def test_cliente_no_ve_pedidos_ajenos(self):
        p = self.pedido()
        self.client.force_login(self.u2)
        self.assertNotContains(self.client.get(reverse("pedidos:mis_pedidos")), f"Pedido #{p.pk}")
        self.assertEqual(self.client.post(reverse("pedidos:cancelar_mio", args=[p.pk])).status_code, 404)

    def test_solicitar_apartado_desde_la_tienda(self):
        self.client.force_login(self.u)
        self.client.post(reverse("tienda:apartar", args=["FRE-001"]), {"cantidad": 1, "nota": "Lo recojo el sábado"})
        sol = SolicitudApartado.objects.get()
        self.assertEqual((sol.cliente, sol.nota_cliente), (self.cliente, "Lo recojo el sábado"))
        self.client.logout()
        self.assertContains(self.client.get(reverse("tienda:producto", args=["FRE-001"])), "Crea tu cuenta")
