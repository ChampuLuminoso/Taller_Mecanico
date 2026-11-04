"""Fase 8: piezas de producción (Railway)."""
from datetime import datetime, time
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings

from .decoradores import ip_de

BOG = ZoneInfo("America/Bogota")


class IpRealTests(TestCase):
    def peticion(self, xff=None):
        extra = {"REMOTE_ADDR": "10.0.0.5"}   # la IP del proxy de Railway
        if xff:
            extra["HTTP_X_FORWARDED_FOR"] = xff
        return RequestFactory().get("/", **extra)

    @override_settings(PROXIES_DE_CONFIANZA=1)
    def test_toma_la_ip_que_agrego_nuestro_proxy(self):
        self.assertEqual(ip_de(self.peticion("186.30.1.2")), "186.30.1.2")

    @override_settings(PROXIES_DE_CONFIANZA=1)
    def test_no_se_deja_engañar_por_una_cabecera_inventada(self):
        # Un atacante manda "X-Forwarded-For: 1.1.1.1"; Railway agrega la IP real al final.
        self.assertEqual(ip_de(self.peticion("1.1.1.1, 186.30.1.2")), "186.30.1.2")

    @override_settings(PROXIES_DE_CONFIANZA=0)
    def test_sin_proxy_usa_la_conexion_directa(self):
        self.assertEqual(ip_de(self.peticion("1.1.1.1")), "10.0.0.5")


class SaludYErroresTests(TestCase):
    def test_salud(self):
        r = self.client.get("/salud/")
        self.assertEqual((r.status_code, r.content), (200, b"ok"))

    def test_pagina_no_encontrada_en_espanol_y_con_la_marca(self):
        r = self.client.get("/no-existe/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "No encontramos esa página", status_code=404)
        self.assertContains(r, "AutoPartes M&amp;F", status_code=404)


class TareasProgramadasTests(TestCase):
    def correr(self, hora):
        salida = StringIO()
        ahora = datetime.combine(datetime(2026, 11, 4).date(), time(hora), tzinfo=BOG)
        with patch("django.utils.timezone.now", return_value=ahora), \
             patch("inventario.management.commands.tareas_programadas.enviar_recordatorios", return_value=2) as rec:
            call_command("tareas_programadas", stdout=salida)
        return salida.getvalue(), rec.called

    def test_recordatorios_solo_desde_las_5_pm(self):
        texto, llamo = self.correr(10)
        self.assertFalse(llamo)
        self.assertIn("recordatorios: 0", texto)
        texto, llamo = self.correr(17)
        self.assertTrue(llamo)
        self.assertIn("recordatorios: 2", texto)
