"""
Cálculo de ventas. Una VENTA es un pedido que el taller confirmó (el inventario
ya salió) y no se canceló. Se cuenta en el momento de la confirmación.

Toda la aritmética de dinero usa Decimal: con float, 0.1 + 0.2 ≠ 0.3,
y en contabilidad un peso perdido es un error.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.utils import formats, timezone

from pedidos.models import Pedido, PedidoItem

DIA, SEMANA, MES = "dia", "semana", "mes"
TIPOS = [(DIA, "Día"), (SEMANA, "Semana"), (MES, "Mes")]
ORDENES = [("precio", "Precio (mayor a menor)"), ("unidades", "Más vendidos"), ("ingreso", "Mayor ingreso")]
CERO = Decimal(0)


@dataclass
class Periodo:
    tipo: str
    inicio: date          # incluido
    fin: date             # excluido
    titulo: str
    anterior: date
    siguiente: date
    nombre_anterior: str  # "el día anterior", "la semana anterior"…

    @property
    def frente_a(self):
        """'frente al día anterior' (a + el = al, como se dice en español)."""
        return "al " + self.nombre_anterior[3:] if self.nombre_anterior.startswith("el ") else "a " + self.nombre_anterior

    def rango_aware(self):
        return (timezone.make_aware(datetime.combine(self.inicio, time.min)),
                timezone.make_aware(datetime.combine(self.fin, time.min)))


def _primero_del_mes(d, desplazamiento=0):
    mes = d.month - 1 + desplazamiento
    return date(d.year + mes // 12, mes % 12 + 1, 1)


def periodo(tipo, fecha):
    hoy = timezone.localdate()
    if tipo == SEMANA:
        inicio = fecha - timedelta(days=fecha.weekday())
        fin = inicio + timedelta(days=7)
        titulo = (f"Semana del {formats.date_format(inicio, 'j M')} al "
                  f"{formats.date_format(fin - timedelta(days=1), 'j M Y')}").replace(".", "").lower().replace("semana", "Semana")
        return Periodo(tipo, inicio, fin, titulo, inicio - timedelta(days=7), fin, "la semana anterior")
    if tipo == MES:
        inicio = _primero_del_mes(fecha)
        fin = _primero_del_mes(fecha, 1)
        return Periodo(tipo, inicio, fin, formats.date_format(inicio, "F Y").capitalize(),
                       _primero_del_mes(fecha, -1), fin, "el mes anterior")
    titulo = "Hoy" if fecha == hoy else ("Ayer" if fecha == hoy - timedelta(days=1) else "")
    titulo = f"{titulo + ', ' if titulo else ''}{formats.date_format(fecha, 'l j \\d\\e F Y').lower()}"
    return Periodo(DIA, fecha, fecha + timedelta(days=1), titulo, fecha - timedelta(days=1),
                   fecha + timedelta(days=1), "el día anterior")


def ventas(desde, hasta):
    """Pedidos confirmados (no cancelados) en el rango [desde, hasta)."""
    return Pedido.objects.filter(estado__in=Pedido.DESCONTADOS, confirmado_en__gte=desde, confirmado_en__lt=hasta)


def _total(qs):
    return qs.aggregate(t=Sum("total"))["t"] or CERO


@dataclass
class Resumen:
    periodo: Periodo
    pedidos: list
    productos: list
    total: Decimal = CERO
    subtotal: Decimal = CERO
    domicilios: Decimal = CERO
    unidades: int = 0
    ganancia: Decimal = CERO
    ganancia_incompleta: bool = False     # algún producto vendido no tenía costo registrado
    por_cobrar: Decimal = CERO
    total_anterior: Decimal = CERO
    barras: list = field(default_factory=list)

    @property
    def cantidad_pedidos(self):
        return len(self.pedidos)

    @property
    def ticket_promedio(self):
        return (self.total / len(self.pedidos)).quantize(Decimal("1")) if self.pedidos else CERO

    @property
    def variacion(self):
        """% contra el periodo anterior; None si antes no hubo ventas (no se puede dividir por cero)."""
        if not self.total_anterior:
            return None
        return ((self.total - self.total_anterior) / self.total_anterior * 100).quantize(Decimal("1"))


def resumen(tipo, fecha, orden="precio"):
    per = periodo(tipo, fecha)
    desde, hasta = per.rango_aware()
    qs = ventas(desde, hasta).select_related("cliente").prefetch_related("items")
    pedidos = list(qs.order_by("confirmado_en"))

    linea = ExpressionWrapper(F("cantidad") * F("precio_unitario"), output_field=DecimalField())
    costo = ExpressionWrapper(F("cantidad") * F("costo_unitario"), output_field=DecimalField())
    productos = list(
        PedidoItem.objects.filter(pedido__in=qs)
        .values("producto_id", "sku", "nombre_producto")
        .annotate(unidades=Sum("cantidad"), ingreso=Sum(linea), costo=Sum(costo),
                  precio=Max("precio_unitario"), sin_costo=Count("id", filter=Q(costo_unitario__isnull=True)))
    )
    claves = {"precio": lambda p: (-p["precio"], p["nombre_producto"]),
              "unidades": lambda p: (-p["unidades"], -p["ingreso"]),
              "ingreso": lambda p: (-p["ingreso"], p["nombre_producto"])}
    productos.sort(key=claves.get(orden, claves["precio"]))
    for p in productos:
        p["ganancia"] = None if p["sin_costo"] else p["ingreso"] - (p["costo"] or CERO)

    r = Resumen(per, pedidos, productos)
    r.total = sum((p.total for p in pedidos), CERO)
    r.subtotal = sum((p.subtotal for p in pedidos), CERO)
    r.domicilios = sum((p.costo_envio for p in pedidos), CERO)
    r.unidades = sum(p["unidades"] for p in productos)
    r.ganancia = sum((p["ganancia"] for p in productos if p["ganancia"] is not None), CERO)
    r.ganancia_incompleta = any(p["ganancia"] is None for p in productos)
    r.por_cobrar = sum((p.total for p in pedidos if not p.pagado), CERO)

    ant = periodo(tipo, per.anterior)
    r.total_anterior = _total(ventas(*ant.rango_aware()))
    r.barras = _barras(per, pedidos)
    return r


def _barras(per, pedidos):
    """Una barra por hora (día) o por día (semana / mes)."""
    sumas = {}
    for p in pedidos:
        local = timezone.localtime(p.confirmado_en)
        clave = local.hour if per.tipo == DIA else local.date()
        sumas[clave] = sumas.get(clave, CERO) + p.total
    if per.tipo == DIA:
        horas = list(sumas) or [8]
        claves = range(min(8, *horas), max(18, *horas) + 1)
        etiqueta = lambda h: f"{h % 12 or 12}{'a' if h < 12 else 'p'}"  # noqa: E731
        largo = lambda h: f"{h % 12 or 12}:00 {'a. m.' if h < 12 else 'p. m.'}"  # noqa: E731
    else:
        claves = [per.inicio + timedelta(days=i) for i in range((per.fin - per.inicio).days)]
        etiqueta = (lambda d: formats.date_format(d, "D j").lower()) if per.tipo == SEMANA else (lambda d: str(d.day))
        largo = lambda d: formats.date_format(d, "l j \\d\\e F").lower()  # noqa: E731
    return [{"etiqueta": etiqueta(k), "largo": largo(k), "valor": sumas.get(k, CERO)} for k in claves]


def _redondo(maximo):
    """Tope 'bonito' para el eje: 87.000 → 100.000; 1.240.000 → 1.500.000."""
    if maximo <= 0:
        return Decimal(100000)
    potencia = Decimal(10) ** (len(str(int(maximo))) - 1)
    for paso in (1, Decimal("1.5"), 2, Decimal("2.5"), 3, 4, 5, 6, 8, 10):
        if potencia * paso >= maximo:
            return potencia * paso
    return potencia * 10


def _compacto(v):
    v = int(v)
    if v >= 1_000_000:
        return f"${v / 1_000_000:g}M".replace(".", ",")
    if v >= 1000:
        return f"${v // 1000}K"
    return f"${v}"


def grafica(barras, ancho=640, alto=220):
    """Geometría del gráfico de columnas en SVG (se dibuja en la plantilla, sin librerías)."""
    izq, der, arriba, abajo = 46, 8, 12, 26
    area_w, area_h = ancho - izq - der, alto - arriba - abajo
    tope = _redondo(max((b["valor"] for b in barras), default=CERO))
    n = max(len(barras), 1)
    hueco = area_w / n
    grosor = min(24, hueco * 0.62)
    paso_etiqueta = 1 if n <= 16 else 5
    columnas = []
    for i, b in enumerate(barras):
        h = float(b["valor"] / tope) * area_h if tope else 0
        x = izq + i * hueco + (hueco - grosor) / 2
        y = arriba + area_h - h
        r = min(4, h, grosor / 2)
        d = (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
             f"H{x + grosor - r:.1f} Q{x + grosor:.1f},{y:.1f} {x + grosor:.1f},{y + r:.1f} V{y + h:.1f} Z") if h > 0 else ""
        columnas.append({**b, "d": d, "hit_x": izq + i * hueco, "hit_w": hueco, "centro": x + grosor / 2,
                         "mostrar_etiqueta": i % paso_etiqueta == 0 or n <= 16})
    lineas = [{"y": arriba + area_h - area_h * f, "texto": _compacto(tope * Decimal(str(f)))} for f in (0, 0.5, 1)]
    return {"ancho": ancho, "alto": alto, "columnas": columnas, "lineas": lineas, "base_y": arriba + area_h,
            "izq": izq, "der": ancho - der, "etiqueta_y": alto - 8, "hit_y": arriba, "hit_h": area_h,
            "vacia": not any(b["valor"] for b in barras)}
