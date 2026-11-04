"""Pruebas de la Fase 2: registro, inicio de sesión, jerarquía de personal y comandos."""
from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.management import CommandError, call_command
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import servicios
from .auditoria import crear_fran
from .models import Auditoria, AuditoriaFran, Cliente, Empleado, Usuario
from .pruebas_util import usuario_con_rol

SISTEMA = settings.TALLER["EMAIL_SISTEMA"]   # usuario técnico creado por migración
CLAVE = "ClaveSegura-2026"


def datos_registro(**cambios):
    hoy = timezone.localdate()
    datos = {
        "nombres": "Carlos", "apellidos": "Gómez", "email": "Carlos@Correo.co", "telefono": "3109876543",
        "fecha_nacimiento": date(hoy.year - 30, 1, 15).isoformat(),
        "password1": CLAVE, "password2": CLAVE, "acepta_politica": "on",
    }
    datos.update(cambios)
    return datos


def personal(creador, rol, email, documento):
    return servicios.crear_personal(creador, rol=rol, email=email, password=CLAVE, nombres="N",
                                    apellidos="A", numero_documento=documento, telefono="3001112233",
                                    cargo="Mecánico")


class RegistroTests(TestCase):
    def test_registro_exitoso_crea_cliente_y_entra(self):
        r = self.client.post(reverse("cuentas:registro"), datos_registro())
        self.assertRedirects(r, reverse("cuentas:panel"))
        c = Cliente.objects.get()
        self.assertEqual(c.usuario.email, "carlos@correo.co")           # correo normalizado
        self.assertEqual(c.usuario.codigos_rol(), {"CLIENTE"})
        self.assertEqual(c.version_politica, "2026-11-v1")
        self.assertIsNotNone(c.acepta_datos_en)
        self.assertNotEqual(c.usuario.password, CLAVE)                   # se guarda el hash

    def test_menor_de_edad_no_puede_registrarse(self):
        hoy = timezone.localdate()
        r = self.client.post(reverse("cuentas:registro"),
                             datos_registro(fecha_nacimiento=date(hoy.year - 17, 1, 1).isoformat()))
        self.assertContains(r, "al menos 18 años")
        self.assertFalse(Usuario.todos.exclude(email=SISTEMA).exists())

    def test_sin_aceptar_politica_no_hay_cuenta(self):
        datos = datos_registro()
        del datos["acepta_politica"]
        r = self.client.post(reverse("cuentas:registro"), datos)
        self.assertContains(r, "debes aceptar la política")
        self.assertFalse(Usuario.todos.exclude(email=SISTEMA).exists())

    def test_clave_debil_rechazada(self):
        r = self.client.post(reverse("cuentas:registro"), datos_registro(password1="12345678", password2="12345678"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.todos.exclude(email=SISTEMA).exists())

    def test_correo_repetido_incluso_el_de_fran(self):
        crear_fran("carlos@correo.co", CLAVE)
        r = self.client.post(reverse("cuentas:registro"), datos_registro())
        self.assertContains(r, "Ya existe una cuenta")
        self.assertEqual(Usuario.todos.exclude(email=SISTEMA).count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.jefe = usuario_con_rol("jefe@taller.co", "JEFE")

    def entrar(self, email="jefe@taller.co", clave=CLAVE, **extra):
        return self.client.post(reverse("cuentas:login"), {"email": email, "password": clave, **extra})

    def test_entrar_y_salir(self):
        self.assertRedirects(self.entrar(), reverse("cuentas:panel"))
        self.assertEqual(self.client.get(reverse("cuentas:logout")).status_code, 405)  # salir solo por POST
        self.client.post(reverse("cuentas:logout"))
        self.assertEqual(self.client.get(reverse("cuentas:panel")).status_code, 302)

    def test_mismo_mensaje_para_todo_error(self):
        self.assertContains(self.entrar(clave="mala"), "Correo o contraseña incorrectos.")
        self.assertContains(self.entrar(email="noexiste@x.co"), "Correo o contraseña incorrectos.")
        self.jefe.bloqueado = True
        self.jefe.save()
        self.assertContains(self.entrar(), "Correo o contraseña incorrectos.")

    def test_freno_tras_cinco_intentos(self):
        for _ in range(5):
            self.entrar(clave="mala")
        self.assertContains(self.entrar(), "Demasiados intentos")   # ni con la clave correcta

    def test_no_redirige_a_sitios_externos(self):
        r = self.entrar(next="https://sitio-malo.com/robar")
        self.assertRedirects(r, reverse("cuentas:panel"))

    def test_inicios_quedan_auditados_y_los_de_fran_aparte(self):
        crear_fran("fran@taller.co", CLAVE)
        self.entrar()
        self.client.post(reverse("cuentas:logout"))
        self.entrar("fran@taller.co")
        self.assertTrue(Auditoria.objects.filter(accion="inicio_sesion", usuario=self.jefe).exists())
        self.assertFalse(Auditoria.objects.filter(usuario__es_fran=True).exists())
        self.assertTrue(AuditoriaFran.objects.filter(accion="inicio_sesion").exists())

    def test_fallo_contra_fran_no_aparece_en_auditoria_de_jefes(self):
        crear_fran("fran@taller.co", CLAVE)
        self.entrar("fran@taller.co", "mala")
        self.assertFalse(Auditoria.objects.filter(despues__email="fran@taller.co").exists())
        self.assertTrue(AuditoriaFran.objects.filter(accion="inicio_sesion_fallido").exists())


class JerarquiaPersonalTests(TestCase):
    def setUp(self):
        self.jefe = usuario_con_rol("jefe@taller.co", "JEFE")
        self.subjefe = usuario_con_rol("sub@taller.co", "SUBJEFE")
        self.empleado = usuario_con_rol("emp@taller.co", "EMPLEADO")
        self.fran = crear_fran("fran@taller.co", CLAVE)

    def test_quien_crea_a_quien(self):
        personal(self.subjefe, "EMPLEADO", "e1@t.co", "1")      # Subjefe → Empleado ✔
        personal(self.jefe, "EMPLEADO", "e2@t.co", "2")         # Jefe → Empleado ✔
        personal(self.jefe, "SUBJEFE", "s1@t.co", "3")          # Jefe → Subjefe ✔
        personal(self.fran, "JEFE", "j1@t.co", "4")             # Fran → Jefe ✔
        for creador, rol in [(self.subjefe, "SUBJEFE"), (self.jefe, "JEFE"), (self.empleado, "EMPLEADO"),
                             (self.jefe, "INGENIERO"), (self.subjefe, "JEFE")]:
            with self.subTest(creador=creador.email, rol=rol), self.assertRaises(PermissionDenied):
                personal(creador, rol, f"x-{rol}-{creador.pk}@t.co", f"9{creador.pk}{rol}")

    def test_formulario_solo_ofrece_roles_permitidos(self):
        self.client.force_login(self.subjefe)
        r = self.client.get(reverse("cuentas:personal_crear"))
        self.assertEqual([c[0] for c in r.context["form"].fields["rol"].choices], ["EMPLEADO"])
        # Aunque alguien manipule el HTML y envíe SUBJEFE, el servidor lo rechaza.
        datos = {"rol": "SUBJEFE", "nombres": "N", "apellidos": "A", "numero_documento": "77", "email": "h@t.co",
                 "telefono": "3001112233", "cargo": "X", "password1": CLAVE, "password2": CLAVE}
        self.client.post(reverse("cuentas:personal_crear"), datos)
        self.assertFalse(Usuario.objects.filter(email="h@t.co").exists())

    def test_jefe_crea_subjefe_por_la_web(self):
        self.client.force_login(self.jefe)
        datos = {"rol": "SUBJEFE", "nombres": "Laura", "apellidos": "Díaz", "numero_documento": "88",
                 "email": "laura@t.co", "telefono": "3001112233", "cargo": "Administradora",
                 "password1": CLAVE, "password2": CLAVE}
        r = self.client.post(reverse("cuentas:personal_crear"), datos)
        self.assertRedirects(r, reverse("cuentas:personal"))
        self.assertEqual(Usuario.objects.get(email="laura@t.co").codigos_rol(), {"SUBJEFE"})
        self.assertTrue(Auditoria.objects.filter(accion="crear_personal", usuario=self.jefe).exists())

    def test_empleado_no_entra_a_personal(self):
        self.client.force_login(self.empleado)
        self.assertEqual(self.client.get(reverse("cuentas:personal")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cuentas:personal_crear")).status_code, 403)

    def test_fran_no_aparece_en_la_lista_de_personal(self):
        Empleado.objects.create(usuario=self.fran, nombres="Fran", apellidos="X", numero_documento="5",
                                telefono="3001112233", cargo="Gerente")
        personal(self.jefe, "EMPLEADO", "e1@t.co", "1")
        self.client.force_login(self.jefe)
        r = self.client.get(reverse("cuentas:personal"))
        self.assertContains(r, "e1@t.co")
        self.assertNotContains(r, "fran@taller.co")


class BloqueoTests(TestCase):
    def setUp(self):
        self.jefe = usuario_con_rol("jefe@taller.co", "JEFE")
        self.jefe2 = usuario_con_rol("jefe2@taller.co", "JEFE")
        self.subjefe = usuario_con_rol("sub@taller.co", "SUBJEFE")
        self.empleado = usuario_con_rol("emp@taller.co", "EMPLEADO")
        self.fran = crear_fran("fran@taller.co", CLAVE)

    def test_jefe_bloquea_y_desbloquea_empleado(self):
        servicios.bloquear(self.jefe, self.empleado.pk, "Ausencias sin aviso")
        self.empleado.refresh_from_db()
        self.assertFalse(self.client.login(username="emp@taller.co", password=CLAVE))
        servicios.desbloquear(self.jefe, self.empleado.pk)
        self.assertTrue(self.client.login(username="emp@taller.co", password=CLAVE))

    def test_limites(self):
        with self.assertRaises(PermissionDenied):
            servicios.bloquear(self.jefe, self.jefe2.pk, "x")          # mismo rango
        with self.assertRaises(PermissionDenied):
            servicios.bloquear(self.subjefe, self.empleado.pk, "x")    # el subjefe no bloquea
        with self.assertRaises(PermissionDenied):
            servicios.bloquear(self.jefe, self.jefe.pk, "x")           # a sí mismo
        with self.assertRaises(Usuario.DoesNotExist):
            servicios.bloquear(self.jefe, self.fran.pk, "x")           # Fran ni siquiera existe para él
        servicios.bloquear(self.fran, self.jefe.pk, "Revisión")         # Fran sí puede con un jefe

    def test_bloqueo_por_la_web_exige_motivo(self):
        self.client.force_login(self.jefe)
        self.client.post(reverse("cuentas:personal_bloqueo", args=[self.empleado.pk]), {"motivo": ""})
        self.empleado.refresh_from_db()
        self.assertFalse(self.empleado.bloqueado)


class ComandosTests(TestCase):
    def test_crear_ingeniero(self):
        with patch("cuentas.management.commands.crear_ingeniero.getpass", return_value=CLAVE):
            call_command("crear_ingeniero", email="Jorge@Correo.co", stdout=open("/dev/null", "w"))
        u = Usuario.objects.get(email="jorge@correo.co")
        self.assertEqual(u.codigos_rol(), {"INGENIERO"})
        self.assertTrue(u.is_superuser)

    def test_crear_fran_solo_una_vez(self):
        with patch("cuentas.management.commands.crear_fran.getpass", return_value=CLAVE):
            call_command("crear_fran", email="fran@taller.co", stdout=open("/dev/null", "w"))
            with self.assertRaises(CommandError):
                call_command("crear_fran", email="otro@taller.co", stdout=open("/dev/null", "w"))
        self.assertEqual(Usuario.todos.filter(es_fran=True).count(), 1)
        self.assertEqual(Usuario.objects.exclude(email=SISTEMA).count(), 0)
