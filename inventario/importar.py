"""
Carga masiva de productos desde Excel.

Flujo: el Jefe descarga la plantilla → la llena → la sube. Primero se revisan
TODAS las filas; si una sola tiene error, no se guarda nada y se muestra la
lista de errores con su número de fila. Si todo está bien, se guarda todo junto.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from cuentas.permisos import requiere_permiso

from .models import Categoria, Compatibilidad, Marca, MovimientoInventario, Producto
from .servicios import mover

COLUMNAS = [
    ("ProductoID", "Obligatorio. Único. Ej.: FRE-PAST-001", 18),
    ("Nombre", "Obligatorio. Ej.: Pastillas de freno delanteras", 38),
    ("Categoría", "Elige de la lista", 16),
    ("Marca del repuesto", "Ej.: Bosch", 18),
    ("Precio de venta", "Obligatorio. Sin puntos ni $. Ej.: 85000", 16),
    ("Costo", "Opcional. Ej.: 60000", 12),
    ("Cantidad inicial", "Unidades que hay hoy. Ej.: 10", 16),
    ("Stock mínimo", "Avisar cuando queden. Ej.: 2", 14),
    ("Compatible con", "Marca Modelo AñoDesde-AñoHasta; separa con ;  Ej.: Chevrolet Spark 2010-2018; Renault Logan", 50),
    ("Descripción", "Opcional", 40),
]
COMPAT_RE = re.compile(r"^(?P<marca>\S+)(?:\s+(?P<modelo>.*?))?(?:\s+(?P<desde>\d{4})(?:\s*-\s*(?P<hasta>\d{4}))?)?$")


def generar_plantilla() -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Productos"
    negrita, fondo = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1D1D1B")
    for col, (titulo, ayuda, ancho) in enumerate(COLUMNAS, start=1):
        celda = hoja.cell(row=1, column=col, value=titulo)
        celda.font, celda.fill = negrita, fondo
        hoja.cell(row=2, column=col, value=ayuda).font = Font(italic=True, color="7A7770")
        hoja.column_dimensions[celda.column_letter].width = ancho
    hoja.freeze_panes = "A3"

    ejemplo = ["FRE-PAST-001", "Pastillas de freno delanteras", "Frenos", "Bosch", 85000, 60000, 10, 2,
               "Chevrolet Spark 2010-2018; Renault Logan 2008-2020", "Juego x4"]
    for col, valor in enumerate(ejemplo, start=1):
        hoja.cell(row=3, column=col, value=valor)

    categorias = ",".join(Categoria.objects.filter(activo=True).values_list("nombre", flat=True))
    lista = DataValidation(type="list", formula1=f'"{categorias}"', allow_blank=True)
    hoja.add_data_validation(lista)
    lista.add("C3:C2000")

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


@dataclass
class Resultado:
    creados: int = 0
    errores: list = field(default_factory=list)   # [(fila, mensaje)]


def _texto(v):
    return "" if v is None else str(v).strip()


def _numero(v, nombre, entero=False, obligatorio=False):
    if v in (None, ""):
        if obligatorio:
            raise ValueError(f"{nombre} es obligatorio")
        return None
    try:
        n = Decimal(str(v).replace("$", "").replace(".", "").replace(",", "").strip()) if isinstance(v, str) else Decimal(str(v))
    except InvalidOperation:
        raise ValueError(f"{nombre} no es un número")
    if n < 0:
        raise ValueError(f"{nombre} no puede ser negativo")
    if entero and n != int(n):
        raise ValueError(f"{nombre} debe ser un número entero")
    return int(n) if entero else n


def _compatibilidades(texto):
    salida = []
    for parte in filter(None, (p.strip() for p in texto.split(";"))):
        m = COMPAT_RE.match(parte)
        if not m:
            raise ValueError(f'no entiendo la compatibilidad "{parte}"')
        desde = int(m["desde"]) if m["desde"] else None
        hasta = int(m["hasta"]) if m["hasta"] else desde
        if desde and hasta and desde > hasta:
            raise ValueError(f'en "{parte}" el año inicial es mayor que el final')
        salida.append({"marca_vehiculo": m["marca"], "modelo": (m["modelo"] or "").strip(),
                       "anio_desde": desde, "anio_hasta": hasta})
    return salida


def leer(archivo):
    """Devuelve (filas_listas, errores) sin guardar nada."""
    try:
        hoja = load_workbook(archivo, read_only=True, data_only=True).active
    except Exception:
        return [], [(0, "No se pudo abrir el archivo. ¿Es la plantilla en formato .xlsx?")]

    categorias = {c.nombre.lower(): c for c in Categoria.objects.all()}
    existentes = set(Producto.objects.values_list("sku", flat=True))
    vistos, filas, errores = set(), [], []

    for n, fila in enumerate(hoja.iter_rows(min_row=3, values_only=True), start=3):
        fila = list(fila) + [None] * (len(COLUMNAS) - len(fila))
        if not any(_texto(v) for v in fila[:len(COLUMNAS)]):
            continue   # fila vacía
        try:
            sku = _texto(fila[0]).upper()
            if not sku:
                raise ValueError("falta el ProductoID")
            if not re.fullmatch(r"[A-Z0-9-]+", sku):
                raise ValueError(f'el ProductoID "{sku}" solo puede tener mayúsculas, números y guiones')
            if sku in existentes:
                raise ValueError(f'el ProductoID "{sku}" ya existe en el inventario')
            if sku in vistos:
                raise ValueError(f'el ProductoID "{sku}" está repetido en el archivo')
            nombre = _texto(fila[1])
            if not nombre:
                raise ValueError("falta el nombre")
            cat_txt = _texto(fila[2])
            if cat_txt and cat_txt.lower() not in categorias:
                raise ValueError(f'la categoría "{cat_txt}" no existe')
            datos = {
                "sku": sku, "nombre": nombre[:150],
                "categoria": categorias.get(cat_txt.lower()) if cat_txt else None,
                "marca": _texto(fila[3])[:60],
                "precio_venta": _numero(fila[4], "El precio", obligatorio=True),
                "costo": _numero(fila[5], "El costo"),
                "cantidad": _numero(fila[6], "La cantidad", entero=True) or 0,
                "stock_minimo": _numero(fila[7], "El stock mínimo", entero=True) or 0,
                "compat": _compatibilidades(_texto(fila[8])),
                "descripcion": _texto(fila[9]),
            }
        except ValueError as e:
            errores.append((n, str(e)[0].upper() + str(e)[1:] + "."))
            continue
        vistos.add(sku)
        filas.append(datos)
    if not filas and not errores:
        errores.append((0, "El archivo no tiene productos (se empieza a leer desde la fila 3)."))
    return filas, errores


@transaction.atomic
def importar(usuario, archivo) -> Resultado:
    requiere_permiso(usuario, "inventario.importar")
    filas, errores = leer(archivo)
    if errores:
        return Resultado(errores=errores)
    for d in filas:
        marca = Marca.objects.get_or_create(nombre=d["marca"])[0] if d["marca"] else None
        p = Producto.objects.create(sku=d["sku"], nombre=d["nombre"], categoria=d["categoria"], marca=marca,
                                    precio_venta=d["precio_venta"], costo=d["costo"],
                                    stock_minimo=d["stock_minimo"], descripcion=d["descripcion"])
        Compatibilidad.objects.bulk_create(Compatibilidad(producto=p, **c) for c in d["compat"])
        if d["cantidad"]:
            mover(p.pk, MovimientoInventario.ENTRADA, d["cantidad"], usuario, "Inventario inicial (Excel)")
    return Resultado(creados=len(filas))
