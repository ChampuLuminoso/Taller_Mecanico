"""Pruebas de la Fase 6: reporte de ventas, Excel, historial de clientes y auditoría."""
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from cuentas.auditoria import crear_fran
from cuentas.models import Direccion
from cuentas.pruebas_util import cliente_con_cuenta, usuario_con_rol
from inventario import servicios as inv
from inventario.models import Producto
from pedidos import servicios as ped
from pedidos.models import Pedido

from . import servicios as s
from .views import buscar_clientes

BOG = ZoneInfo("America/Bogota")
MAR3, MIE4 = date(2026, 11, 3), date(2026, 11, 4)


def reloj(d, h, m=0):
    return patch("django.utils.timezone.now", return_value=datetime.combine(d, time(h, m), tzinfo=BOG))


class Base(TestCase):
    def setUp(self):
        self.empleado = usuario_con_rol("emp@t.co", "EMPLEADO")
        self.subjefe = usuario_con_rol("sub@t.co", "SUBJEFE")
        self.jefe = usuario_con_rol("jefe@t.co", "JEFE")
        self.ing = usuario_con_rol("ing@t.co", "INGENIERO")
        self.fran = crear_fran("fran@t.co", "ClaveSegura-2026")
        self.u, self.cliente = cliente_con_cuenta()
        self.cliente.numero_documento, self.cliente.tipo_documento = "1020304050", "CC"
        self.cliente.save()
        self.u2, self.otro = cliente_con_cuenta("otro@correo.co", "Luis", "Pérez")
        self.otro.telefono = "3119876543"
        self.otro.save()
        self.disco = Producto.objects.create(sku="FRE-DIS", nombre="Disco de freno", precio_venta=Decimal("160000"),
                                             costo=Decimal("110000"))
        self.filtro = Producto.objects.create(sku="FIL-01", nombre="Filtro de aire", precio_venta=Decimal("35000"),
                                              costo=Decimal("20000"))
        self.bujias = Producto.objects.create(sku="ELE-04", nombre="Bujías x4", precio_venta=Decimal("68000"))  # sin costo
        for p in (self.disco, self.filtro, self.bujias):
            inv.registrar_entrada(p.pk, 50, self.jefe, "Compra")
        Direccion.objects.create(cliente=self.cliente, localidad="Suba", barrio="Niza", direccion="Cl 127", principal=True)

    def venta(self, dia, hora, lineas, usuario=None, cliente=None, envio=True, confirmar=True):
        usuario, cliente = usuario or self.u, cliente or self.cliente
        with reloj(dia, hora):
            p = ped.crear_pedido(usuario, cliente, [(prod.pk, n) for prod, n in lineas],
                                 modalidad=Pedido.ENVIO if envio else Pedido.RECOGER,
                                 metodo_pago=Pedido.CONTRA_ENTREGA if envio else Pedido.EN_TIENDA,
                                 telefono=cliente.telefono, direccion=cliente.direcciones.first() if envio else None)
            if confirmar:
                ped.confirmar(p.pk, self.jefe)
        # creado_en usa el reloj real (su default se fija al cargar el modelo): lo alineamos con la prueba.
        Pedido.objects.filter(pk=p.pk).update(creado_en=datetime.combine(dia, time(hora), tzinfo=BOG))
        return p


class ResumenTests(Base):
    def setUp(self):
        super().setUp()
        self.venta(MAR3, 9, [(self.filtro, 2)])                                   # 70.000 + 2.000
        self.venta(MIE4, 10, [(self.disco, 1), (self.filtro, 1)])                 # 195.000 + 2.000
        self.venta(MIE4, 15, [(self.bujias, 1)], self.u2, self.otro, envio=False)  # 68.000
        cancelado = self.venta(MIE4, 16, [(self.disco, 3)])
        with reloj(MIE4, 17):
            ped.cancelar(cancelado.pk, self.jefe, "No contestó")
        self.venta(MIE4, 11, [(self.disco, 5)], confirmar=False)                  # sin confirmar: no es venta

    def test_dia_con_comparacion_y_ganancia(self):
        with reloj(MIE4, 18):
            r = s.resumen("dia", MIE4)
        self.assertEqual((r.total, r.cantidad_pedidos, r.unidades, r.domicilios),
                         (Decimal("265000"), 2, 3, Decimal("2000")))
        self.assertEqual(r.total_anterior, Decimal("72000"))
        self.assertEqual(r.variacion, Decimal("268"))            # (265−72)/72 = +268 %
        # Ganancia: disco 160−110 = 50.000; filtro 35−20 = 15.000; bujías sin costo → no suma y avisa.
        self.assertEqual(r.ganancia, Decimal("65000"))
        self.assertTrue(r.ganancia_incompleta)
        self.assertEqual(r.por_cobrar, Decimal("265000"))

    def test_productos_de_mayor_a_menor_precio(self):
        with reloj(MIE4, 18):
            r = s.resumen("dia", MIE4)
            self.assertEqual([p["sku"] for p in r.productos], ["FRE-DIS", "ELE-04", "FIL-01"])
            r = s.resumen("semana", MIE4, orden="unidades")
            self.assertEqual(r.productos[0]["sku"], "FIL-01")    # 3 filtros en la semana

    def test_semana_y_mes(self):
        with reloj(MIE4, 18):
            semana = s.resumen("semana", MIE4)
            mes = s.resumen("mes", MIE4)
        self.assertEqual(semana.periodo.inicio, date(2026, 11, 2))  # lunes
        self.assertEqual((semana.total, mes.total), (Decimal("337000"), Decimal("337000")))
        self.assertEqual(len(semana.barras), 7)
        self.assertEqual(len(mes.barras), 30)
        self.assertEqual(mes.barras[3]["valor"], Decimal("265000"))  # 4 de noviembre

    def test_barras_por_hora_y_geometria(self):
        with reloj(MIE4, 18):
            r = s.resumen("dia", MIE4)
        por_hora = {b["etiqueta"]: b["valor"] for b in r.barras}
        self.assertEqual((por_hora["10a"], por_hora["3p"], por_hora["11a"]), (Decimal("197000"), Decimal("68000"), 0))
        g = s.grafica(r.barras)
        self.assertEqual(g["lineas"][-1]["texto"], "$200K")      # tope redondo del eje
        self.assertTrue(all(c["d"] == "" for c in g["columnas"] if not c["valor"]))

    def test_precio_y_costo_quedan_congelados(self):
        self.disco.precio_venta, self.disco.costo = Decimal("999000"), Decimal("1")
        self.disco.save()
        with reloj(MIE4, 18):
            r = s.resumen("dia", MIE4)
        disco = next(p for p in r.productos if p["sku"] == "FRE-DIS")
        self.assertEqual((disco["precio"], disco["ganancia"]), (Decimal("160000"), Decimal("50000")))


class PantallasVentasTests(Base):
    def test_solo_jefe_y_fran(self):
        for u, codigo in [(self.empleado, 403), (self.subjefe, 403), (self.ing, 403), (self.u, 403),
                          (self.jefe, 200), (self.fran, 200)]:
            self.client.force_login(u)
            with self.subTest(u=u.email):
                self.assertEqual(self.client.get(reverse("reportes:ventas")).status_code, codigo)
                self.assertEqual(self.client.get(reverse("reportes:exportar")).status_code, codigo)

    def test_por_defecto_es_hoy_y_excel(self):
        self.venta(MIE4, 10, [(self.disco, 1)])
        self.client.force_login(self.jefe)
        with reloj(MIE4, 18):
            r = self.client.get(reverse("reportes:ventas"))
            self.assertContains(r, "Hoy, miércoles 4 de noviembre 2026")
            self.assertContains(r, "$162.000")
            self.assertContains(r, "Disco de freno")
            x = self.client.get(reverse("reportes:exportar"))
        self.assertIn("ventas_dia_2026-11-04.xlsx", x["Content-Disposition"])
        libro = load_workbook(BytesIO(x.content))
        self.assertEqual(libro.sheetnames, ["Resumen", "Productos", "Pedidos"])
        self.assertEqual(libro["Resumen"]["B3"].value, 162000)
        self.assertEqual(libro["Productos"]["F2"].value, 50000)   # ganancia del disco

    def test_panel_del_jefe_muestra_ventas_de_hoy(self):
        self.venta(MIE4, 10, [(self.filtro, 1)])
        with reloj(MIE4, 18):
            self.client.force_login(self.jefe)
            self.assertContains(self.client.get(reverse("cuentas:panel")), "Ventas de hoy")
            self.client.force_login(self.subjefe)
            self.assertNotContains(self.client.get(reverse("cuentas:panel")), "Ventas de hoy")


class HistorialTests(Base):
    def test_buscar_por_nombre_cedula_o_telefono(self):
        self.assertEqual(list(buscar_clientes("ana rojas")), [self.cliente])
        self.assertEqual(list(buscar_clientes("1020304050")), [self.cliente])
        self.assertEqual(list(buscar_clientes("311 987 6543")), [self.otro])
        self.assertEqual(list(buscar_clientes("an")), [])          # muy corto

    def test_historial_con_compras_y_filtro_de_fechas(self):
        self.venta(MAR3, 9, [(self.filtro, 2)])
        self.venta(MIE4, 10, [(self.disco, 1)])
        self.client.force_login(self.jefe)
        r = self.client.get(reverse("reportes:cliente", args=[self.cliente.pk]))
        self.assertEqual((r.context["total_comprado"], r.context["compras"]), (Decimal("234000"), 2))
        r = self.client.get(reverse("reportes:cliente", args=[self.cliente.pk]), {"desde": "2026-11-04"})
        self.assertEqual(r.context["compras"], 1)
        self.client.force_login(self.subjefe)
        self.assertEqual(self.client.get(reverse("reportes:clientes")).status_code, 403)


class AuditoriaTests(Base):
    def test_jefe_no_ve_a_fran_y_fran_ve_todo(self):
        p = self.venta(MIE4, 10, [(self.filtro, 1)], confirmar=False)
        with reloj(MIE4, 11):
            ped.cancelar(p.pk, self.fran, "Decisión de gerencia")
        self.client.force_login(self.jefe)
        with reloj(MIE4, 18):
            r = self.client.get(reverse("reportes:auditoria"))
            self.assertContains(r, "crear_pedido")
            self.assertNotContains(r, "Decisión de gerencia")
            self.client.force_login(self.fran)
            r = self.client.get(reverse("reportes:auditoria"))
            self.assertContains(r, "Decisión de gerencia")
            self.assertContains(r, "Gerencia")
