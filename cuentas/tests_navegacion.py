"""Fase 7: el menú (y por lo tanto el orden del deslizamiento) depende del rol."""
from django.test import TestCase
from django.urls import reverse

from cuentas.auditoria import crear_fran
from cuentas.pruebas_util import cliente_con_cuenta, usuario_con_rol


def menu(respuesta):
    return [s["nombre"] for s in respuesta.context["menu_secciones"]]


class MenuTests(TestCase):
    def test_visitante(self):
        r = self.client.get(reverse("tienda:catalogo"))
        self.assertEqual(menu(r), ["Tienda", "Agendar cita", "Carrito", "Entrar"])
        self.assertEqual(r.context["seccion_activa"], 0)
        self.assertContains(r, 'data-seccion="0"')
        self.assertContains(r, "AutoPartes M&amp;F")

    def test_cliente(self):
        u, _ = cliente_con_cuenta()
        self.client.force_login(u)
        r = self.client.get(reverse("citas:mis_citas"))
        self.assertEqual(menu(r), ["Tienda", "Mis citas", "Mis pedidos", "Carrito", "Mi cuenta"])
        self.assertEqual(r.context["seccion_activa"], 1)

    def test_empleado_no_ve_ventas_ni_personal(self):
        self.client.force_login(usuario_con_rol("e@t.co", "EMPLEADO"))
        r = self.client.get(reverse("inventario:lista"))
        self.assertEqual(menu(r), ["Panel", "Inventario", "Pedidos", "Agenda", "Apartados", "Tienda"])
        self.assertEqual(r.context["seccion_activa"], 1)

    def test_jefe_y_fran_ven_todo_y_la_seccion_mas_especifica_gana(self):
        for u in (usuario_con_rol("j@t.co", "JEFE"), crear_fran("f@t.co", "ClaveSegura-2026")):
            self.client.force_login(u)
            r = self.client.get(reverse("reportes:ventas"))
            self.assertEqual(menu(r), ["Panel", "Inventario", "Pedidos", "Agenda", "Apartados", "Ventas",
                                       "Clientes", "Personal", "Tienda"])
            self.assertEqual(r.context["seccion_activa"], 5)

    def test_paginas_fuera_del_menu_no_deslizan(self):
        r = self.client.get(reverse("cuentas:registro"))
        self.assertContains(r, 'data-seccion="-1"')

    def test_carrito_muestra_cuantas_unidades_lleva(self):
        from inventario.models import Producto
        p = Producto.objects.create(sku="X-1", nombre="X", precio_venta=1000)
        jefe = usuario_con_rol("j2@t.co", "JEFE")
        from inventario.servicios import registrar_entrada
        registrar_entrada(p.pk, 5, jefe, "Compra")
        self.client.post(reverse("tienda:agregar", args=[p.pk]), {"cantidad": 3})
        r = self.client.get(reverse("tienda:catalogo"))
        carrito = next(s for s in r.context["menu_secciones"] if s["nombre"] == "Carrito")
        self.assertEqual(carrito["insignia"], 3)
