"""Exporte del reporte de ventas a Excel: Resumen, Productos y Pedidos, con formato de pesos."""
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

PESOS = '"$"#,##0'
ENCABEZADO = (Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1D1D1B"))


def _hoja(libro, titulo, columnas, filas, formatos=None):
    hoja = libro.create_sheet(titulo)
    hoja.append(columnas)
    for c in hoja[1]:
        c.font, c.fill = ENCABEZADO
    for f in filas:
        hoja.append(f)
    for i, col in enumerate(columnas, start=1):
        letra = get_column_letter(i)
        largo = max([len(str(col))] + [len(str(f[i - 1])) for f in filas if f[i - 1] is not None] or [10])
        hoja.column_dimensions[letra].width = min(max(largo + 2, 10), 48)
        if formatos and formatos.get(i):
            for celda in hoja[letra][1:]:
                celda.number_format = formatos[i]
    hoja.freeze_panes = "A2"
    return hoja


def generar(r, con_ganancia):
    libro = Workbook()
    libro.remove(libro.active)

    resumen = [
        ("Periodo", r.periodo.titulo),
        ("Total vendido", r.total),
        ("Productos", r.subtotal),
        ("Domicilios", r.domicilios),
        ("Pedidos", r.cantidad_pedidos),
        ("Unidades", r.unidades),
        ("Ticket promedio", r.ticket_promedio),
        ("Por cobrar (aún no entregado)", r.por_cobrar),
        (f"Total {r.periodo.nombre_anterior}", r.total_anterior),
    ]
    if con_ganancia:
        resumen.append(("Ganancia" + (" (incompleta: hay productos sin costo)" if r.ganancia_incompleta else ""),
                        r.ganancia))
    hoja = _hoja(libro, "Resumen", ["Concepto", "Valor"], resumen)
    for fila in hoja.iter_rows(min_row=2):
        if fila[0].value not in ("Periodo", "Pedidos", "Unidades"):
            fila[1].number_format = PESOS

    columnas = ["ProductoID", "Producto", "Precio", "Unidades", "Ingreso"]
    filas = [[p["sku"], p["nombre_producto"], p["precio"], p["unidades"], p["ingreso"]] for p in r.productos]
    formatos = {3: PESOS, 5: PESOS}
    if con_ganancia:
        columnas.append("Ganancia")
        for f, p in zip(filas, r.productos):
            f.append(p["ganancia"])
        formatos[6] = PESOS
    _hoja(libro, "Productos", columnas, filas, formatos)

    _hoja(libro, "Pedidos",
          ["Pedido", "Confirmado", "Cliente", "Entrega", "Pago", "Estado", "Productos", "Domicilio", "Total", "Pagado"],
          [[p.pk, timezone.localtime(p.confirmado_en).strftime("%d/%m/%Y %H:%M"), str(p.cliente),
            p.get_modalidad_display(), p.get_metodo_pago_display(), p.get_estado_display(),
            p.subtotal, p.costo_envio, p.total, "Sí" if p.pagado else "No"] for p in r.pedidos],
          {7: PESOS, 8: PESOS, 9: PESOS})

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()
