"""Pruebas de la Fase 3: pantallas de inventario, alertas, Excel y apartados."""
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook, load_workbook
from PIL import Image

from cuentas.auditoria import crear_fran
from cuentas.models import Auditoria
from cuentas.pruebas_util import cliente_con_cuenta, usuario_con_rol

from . import servicios as s
from .importar import generar_plantilla
from .models import Apartado, Categoria, MovimientoInventario as M, Producto, SolicitudApartado

MEDIA_TEMPORAL = tempfile.mkdtemp()


def excel(filas):
    """Arma un .xlsx como la plantilla: encabezado, fila de ayuda y datos desde la fila 3."""
    libro = Workbook()
    hoja = libro.active
    hoja.append(["ProductoID"])
    hoja.append(["ayuda"])
    for f in filas:
        hoja.append(f)
    salida = BytesIO()
    libro.save(salida)
    return SimpleUploadedFile("productos.xlsx", salida.getvalue())


class Base(TestCase):
    def setUp(self):
        self.empleado = usuario_con_rol("emp@t.co", "EMPLEADO")
        self.subjefe = usuario_con_rol("sub@t.co", "SUBJEFE")
        self.jefe = usuario_con_rol("jefe@t.co", "JEFE")
        self.fran = crear_fran("fran@t.co", "ClaveSegura-2026")
        self.usuario_cliente, self.cliente = cliente_con_cuenta()
        self.frenos = Categoria.objects.get(nombre="Frenos")
        self.p = Producto.objects.create(sku="FRE-001", nombre="Pastillas de freno", categoria=self.frenos,
                                         precio_venta=Decimal("85000"), stock_minimo=2)


class PermisosInventarioTests(Base):
    def test_solo_el_jefe_registra_entradas_y_ajustes(self):
        for u in (self.empleado, self.subjefe):
            with self.subTest(u=u.email):
                with self.assertRaises(PermissionDenied):
                    s.registrar_entrada(self.p.pk, 5, u, "Compra")
                with self.assertRaises(PermissionDenied):
                    s.ajustar(self.p.pk, 1, -1, u, "Conteo")
        s.registrar_entrada(self.p.pk, 5, self.jefe, "Compra")
        s.ajustar(self.p.pk, 1, -1, self.jefe, "Conteo")
        self.p.refresh_from_db()
        self.assertEqual(self.p.cantidad_fisica, 4)

    def test_categorias_reales(self):
        self.assertEqual(set(Categoria.objects.values_list("nombre", flat=True)),
                         {"Frenos", "Suspensión", "Motor", "Eléctricos", "Filtros", "Aceites"})

    def test_pantallas_segun_rol(self):
        self.client.force_login(self.empleado)
        self.assertEqual(self.client.get(reverse("inventario:lista")).status_code, 200)
        r = self.client.get(reverse("inventario:detalle", args=[self.p.pk]))
        self.assertNotContains(r, "Registrar entrada")
        self.assertEqual(self.client.get(reverse("inventario:nuevo")).status_code, 403)
        self.assertEqual(self.client.post(reverse("inventario:entrada", args=[self.p.pk]),
                                          {"cantidad": 5, "motivo": "x"}).status_code, 403)
        self.client.force_login(self.jefe)
        self.assertContains(self.client.get(reverse("inventario:detalle", args=[self.p.pk])), "Registrar entrada")


class AlertaStockTests(Base):
    def test_avisa_una_vez_al_cruzar_el_minimo(self):
        s.registrar_entrada(self.p.pk, 5, self.jefe, "Compra")
        with self.captureOnCommitCallbacks(execute=True):
            s.mover(self.p.pk, M.VENTA, 2, self.empleado, "Venta")   # quedan 3: aún no
        self.assertEqual(len(mail.outbox), 0)
        with self.captureOnCommitCallbacks(execute=True):
            s.mover(self.p.pk, M.VENTA, 1, self.empleado, "Venta")   # quedan 2: cruza
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertIn("Pastillas de freno", correo.subject)
        self.assertEqual(set(correo.bcc), {"jefe@t.co", "fran@t.co"})   # ni empleado ni subjefe
        with self.captureOnCommitCallbacks(execute=True):
            s.mover(self.p.pk, M.VENTA, 1, self.empleado, "Venta")   # ya estaba bajo: no repite
        self.assertEqual(len(mail.outbox), 1)

    def test_apartar_tambien_cuenta(self):
        s.registrar_entrada(self.p.pk, 3, self.jefe, "Compra")
        with self.captureOnCommitCallbacks(execute=True):
            s.crear_apartado(self.p, self.cliente, 1, self.subjefe)    # disponible 2 = mínimo
        self.assertEqual(len(mail.outbox), 1)

    def test_panel_muestra_stock_bajo(self):
        s.registrar_entrada(self.p.pk, 1, self.jefe, "Compra")
        self.client.force_login(self.empleado)
        r = self.client.get(reverse("cuentas:panel"))
        self.assertContains(r, "Stock bajo")
        self.assertContains(r, "Pastillas de freno")


class ListaTests(Base):
    def test_busqueda_por_vehiculo_y_respuesta_parcial_htmx(self):
        self.p.compatibilidades.create(marca_vehiculo="Chevrolet", modelo="Spark", anio_desde=2010, anio_hasta=2018)
        Producto.objects.create(sku="ACE-001", nombre="Aceite 20W50", precio_venta=40000)
        self.client.force_login(self.empleado)
        r = self.client.get(reverse("inventario:lista"), {"q": "spark"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "<html")              # solo la tabla
        self.assertContains(r, "Pastillas de freno")
        self.assertNotContains(r, "Aceite 20W50")

    def test_edicion_rapida_guarda_y_audita(self):
        self.client.force_login(self.subjefe)
        r = self.client.post(reverse("inventario:fila", args=[self.p.pk]),
                             {"precio_venta": "90000", "stock_minimo": "3", "activo": "on"})
        self.assertContains(r, "$90.000")
        self.p.refresh_from_db()
        self.assertEqual(self.p.precio_venta, Decimal("90000"))
        reg = Auditoria.objects.get(accion="editar_producto")
        self.assertEqual(reg.antes, {"precio_venta": "85000.00", "stock_minimo": "2"})


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class FormularioProductoTests(Base):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)
        super().tearDownClass()

    def test_crear_con_foto_y_compatibilidad(self):
        buffer = BytesIO()
        Image.new("RGB", (3000, 2000), "red").save(buffer, "PNG")
        foto = SimpleUploadedFile("foto.png", buffer.getvalue(), content_type="image/png")
        datos = {"sku": "sus-amort-01", "nombre": "Amortiguador delantero", "categoria": Categoria.objects.get(nombre="Suspensión").pk,
                 "precio_venta": "210000", "stock_minimo": "1", "activo": "on", "imagen": foto,
                 "compat-TOTAL_FORMS": "1", "compat-INITIAL_FORMS": "0",
                 "compat-0-marca_vehiculo": "Renault", "compat-0-modelo": "Logan",
                 "compat-0-anio_desde": "2008", "compat-0-anio_hasta": "2020"}
        self.client.force_login(self.subjefe)
        r = self.client.post(reverse("inventario:nuevo"), datos)
        p = Producto.objects.get(sku="SUS-AMORT-01")
        self.assertRedirects(r, reverse("inventario:detalle", args=[p.pk]))
        self.assertTrue(p.imagen.name.endswith(".webp"))
        with Image.open(p.imagen.path) as img:
            self.assertEqual(max(img.size), 1200)
        self.assertEqual(p.compatibilidades.get().modelo, "Logan")
        self.assertEqual(p.cantidad_fisica, 0)


class ExcelTests(Base):
    def test_plantilla_tiene_encabezados_y_lista_de_categorias(self):
        hoja = load_workbook(BytesIO(generar_plantilla())).active
        self.assertEqual(hoja["A1"].value, "ProductoID")
        self.assertIn("Frenos", hoja.data_validations.dataValidation[0].formula1)
        self.client.force_login(self.jefe)
        self.assertEqual(self.client.get(reverse("inventario:plantilla")).status_code, 200)

    def test_importa_todo_cuando_no_hay_errores(self):
        archivo = excel([
            ["FIL-AIRE-01", "Filtro de aire", "Filtros", "Mann", 35000, 22000, 8, 2, "Chevrolet Spark 2010-2018; Kia Picanto", ""],
            ["ace-20w50", "Aceite 20W50 galón", "aceites", "", "48.000", None, None, None, None, None],
        ])
        self.client.force_login(self.jefe)
        r = self.client.post(reverse("inventario:importar"), {"archivo": archivo})
        self.assertRedirects(r, reverse("inventario:lista"))
        filtro = Producto.objects.get(sku="FIL-AIRE-01")
        self.assertEqual((filtro.cantidad_fisica, filtro.marca.nombre, filtro.compatibilidades.count()), (8, "Mann", 2))
        self.assertEqual(filtro.movimientos.get().motivo, "Inventario inicial (Excel)")
        aceite = Producto.objects.get(sku="ACE-20W50")
        self.assertEqual((aceite.precio_venta, aceite.cantidad_fisica, aceite.categoria.nombre), (Decimal("48000"), 0, "Aceites"))

    def test_un_error_y_no_se_guarda_nada(self):
        archivo = excel([
            ["MOT-001", "Correa de distribución", "Motor", "", 120000, None, 3, 1, None, None],
            ["FRE-001", "Repetido con el inventario", "Frenos", "", 1000, None, 1, 0, None, None],
            ["X 1", "SKU con espacio", "Frenos", "", 1000, None, None, None, None, None],
            ["MOT-002", "Sin precio", "Motor", "", None, None, None, None, None, None],
            ["MOT-003", "Categoría rara", "Llantas", "", 5000, None, None, None, None, None],
            ["MOT-001", "Repetido en el archivo", "Motor", "", 5000, None, None, None, None, None],
        ])
        self.client.force_login(self.jefe)
        r = self.client.post(reverse("inventario:importar"), {"archivo": archivo})
        errores = dict(r.context["resultado"].errores)
        self.assertEqual(sorted(errores), [4, 5, 6, 7, 8])
        self.assertIn("ya existe", errores[4])
        self.assertIn("Llantas", errores[7])
        self.assertFalse(Producto.objects.filter(sku="MOT-001").exists())

    def test_subjefe_no_importa(self):
        self.client.force_login(self.subjefe)
        self.assertEqual(self.client.get(reverse("inventario:importar")).status_code, 403)


class ApartadosPantallasTests(Base):
    def setUp(self):
        super().setUp()
        s.registrar_entrada(self.p.pk, 5, self.jefe, "Compra")

    def test_flujo_completo_por_pantallas(self):
        sol = s.solicitar_apartado(self.cliente, self.p, 2, "Lo recojo el sábado", self.usuario_cliente)
        self.client.force_login(self.empleado)
        self.assertEqual(self.client.get(reverse("apartados:solicitudes")).status_code, 403)

        self.client.force_login(self.subjefe)
        r = self.client.get(reverse("apartados:solicitudes"))
        self.assertContains(r, "Lo recojo el sábado")
        self.assertContains(r, "wa.me/573001234567")
        self.client.post(reverse("apartados:responder", args=[sol.pk]), {"decision": "aprobar", "abono": "20000"})
        apartado = Apartado.objects.get()
        self.assertEqual(apartado.abono, Decimal("20000"))

        self.client.force_login(self.empleado)   # el empleado entrega, pero no cancela
        self.client.post(reverse("apartados:cerrar", args=[apartado.pk]), {"estado": "CANCELADO"})
        apartado.refresh_from_db()
        self.assertEqual(apartado.estado, "ACTIVO")
        self.client.post(reverse("apartados:cerrar", args=[apartado.pk]), {"estado": "ENTREGADO"})
        apartado.refresh_from_db()
        self.p.refresh_from_db()
        self.assertEqual((apartado.estado, self.p.cantidad_fisica), ("ENTREGADO", 3))

    def test_rechazar(self):
        sol = s.solicitar_apartado(self.cliente, self.p, 1, "", self.usuario_cliente)
        self.client.force_login(self.jefe)
        self.client.post(reverse("apartados:responder", args=[sol.pk]),
                         {"decision": "rechazar", "respuesta": "Ese lo tenemos reservado para el taller"})
        sol.refresh_from_db()
        self.assertEqual(sol.estado, SolicitudApartado.RECHAZADA)
        self.assertFalse(Apartado.objects.exists())

    def test_apartado_directo_por_celular(self):
        self.client.force_login(self.subjefe)
        r = self.client.post(reverse("apartados:nuevo"),
                             {"sku": "fre-001", "cliente": "300 123 4567", "cantidad": 1, "abono": 0})
        self.assertRedirects(r, reverse("apartados:lista"))
        self.assertEqual(Apartado.objects.get().cliente, self.cliente)
        r = self.client.post(reverse("apartados:nuevo"), {"sku": "FRE-001", "cliente": "3119999999", "cantidad": 1})
        self.assertContains(r, "No encontramos ese cliente")

    def test_comando_nocturno_vence_con_usuario_sistema(self):
        a = s.crear_apartado(self.p, self.cliente, 1, self.subjefe)
        Apartado.objects.filter(pk=a.pk).update(vence_en=a.vence_en - timedelta(days=30))
        call_command("vencer_apartados", stdout=StringIO())
        a.refresh_from_db()
        self.assertEqual(a.estado, "VENCIDO")
        mov = self.p.movimientos.filter(tipo=M.LIBERACION).get()
        self.assertEqual(mov.usuario.nombre_visible, "Sistema automático")
