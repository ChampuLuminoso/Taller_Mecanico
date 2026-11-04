from datetime import date, datetime, time, timedelta

from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from citas.avisos import hora_co
from cuentas.auditoria import auditoria_para
from cuentas.decoradores import permiso_requerido
from cuentas.models import Auditoria, Cliente
from cuentas.permisos import tiene_permiso
from pedidos.models import Pedido

from . import excel, servicios
from .servicios import DIA, ORDENES, TIPOS


def _fecha(valor, por_defecto=None):
    try:
        return date.fromisoformat(valor) if valor else por_defecto
    except ValueError:
        return por_defecto


def _parametros(request):
    tipo = request.GET.get("ver", DIA)
    tipo = tipo if tipo in dict(TIPOS) else DIA
    hoy = timezone.localdate()
    fecha = min(_fecha(request.GET.get("fecha"), hoy), hoy)   # el futuro no tiene ventas
    orden = request.GET.get("orden", "precio")
    return tipo, fecha, orden if orden in dict(ORDENES) else "precio"


# ───────────────────────── Ventas ─────────────────────────

@permiso_requerido("reportes.ver")
def ventas(request):
    tipo, fecha, orden = _parametros(request)
    r = servicios.resumen(tipo, fecha, orden)
    hoy = timezone.localdate()
    for p in r.pedidos:
        p.hora_texto = hora_co(p.confirmado_en)
    return render(request, "reportes/ventas.html", {
        "r": r, "tipo": tipo, "fecha": fecha, "orden": orden, "tipos": TIPOS, "ordenes": ORDENES,
        "grafica": servicios.grafica(r.barras), "hay_siguiente": r.periodo.siguiente <= hoy,
        "ver_ganancia": tiene_permiso(request.user, "contabilidad.ver"),
        "puede_exportar": tiene_permiso(request.user, "reportes.exportar"),
        "variacion_abs": abs(r.variacion) if r.variacion is not None else None,
    })


@permiso_requerido("reportes.exportar")
def exportar(request):
    tipo, fecha, orden = _parametros(request)
    r = servicios.resumen(tipo, fecha, orden)
    contenido = excel.generar(r, con_ganancia=tiene_permiso(request.user, "contabilidad.ver"))
    nombre = f"ventas_{tipo}_{r.periodo.inicio:%Y-%m-%d}.xlsx"
    respuesta = HttpResponse(contenido, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


# ───────────────────────── Historial de clientes ─────────────────────────

def buscar_clientes(texto):
    """Por nombre (cada palabra en nombres o apellidos), cédula o teléfono. Nada más."""
    texto = (texto or "").strip()
    if len(texto) < 3:
        return Cliente.objects.none()
    qs = Cliente.objects.filter(anonimizado_en__isnull=True)
    digitos = "".join(c for c in texto if c.isdigit())
    if digitos and len(digitos) >= 5 and len(digitos) == len(texto.replace(" ", "")):
        return qs.filter(Q(numero_documento=digitos) | Q(telefono__endswith=digitos[-10:]))
    for palabra in texto.split()[:4]:
        qs = qs.filter(Q(nombres__icontains=palabra) | Q(apellidos__icontains=palabra))
    return qs


@permiso_requerido("clientes.ver_historial")
def clientes(request):
    q = request.GET.get("q", "")
    resultados = buscar_clientes(q).order_by("nombres", "apellidos")[:50]
    return render(request, "reportes/clientes.html", {"q": q, "resultados": resultados,
                                                      "busco": len(q.strip()) >= 3})


@permiso_requerido("clientes.ver_historial")
def cliente(request, pk):
    c = get_object_or_404(Cliente.objects.filter(anonimizado_en__isnull=True), pk=pk)
    desde, hasta = _fecha(request.GET.get("desde")), _fecha(request.GET.get("hasta"))

    def rango(qs, campo):
        if desde:
            qs = qs.filter(**{f"{campo}__gte": timezone.make_aware(datetime.combine(desde, time.min))})
        if hasta:
            qs = qs.filter(**{f"{campo}__lt": timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min))})
        return qs

    pedidos = rango(c.pedidos.prefetch_related("items"), "creado_en").order_by("-creado_en")
    comprado = pedidos.filter(estado__in=Pedido.DESCONTADOS)
    return render(request, "reportes/cliente.html", {
        "c": c, "desde": desde, "hasta": hasta, "pedidos": pedidos,
        "total_comprado": comprado.aggregate(t=Sum("total"))["t"] or 0, "compras": comprado.count(),
        "apartados": rango(c.apartados.select_related("producto"), "creado_en").order_by("-creado_en"),
        "solicitudes": rango(c.solicitudes_apartado.select_related("producto"), "creado_en").order_by("-creado_en"),
        "citas": rango(c.citas.select_related("tipo_visita", "vehiculo"), "inicio").order_by("-inicio"),
        "vehiculos": c.vehiculos.filter(activo=True),
    })


# ───────────────────────── Auditoría ─────────────────────────

@permiso_requerido("auditoria.ver")
def auditoria(request):
    hoy = timezone.localdate()
    desde = _fecha(request.GET.get("desde"), hoy - timedelta(days=6))
    hasta = _fecha(request.GET.get("hasta"), hoy)
    accion = request.GET.get("accion", "")
    registros = auditoria_para(
        request.user,
        timezone.make_aware(datetime.combine(desde, time.min)),
        timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min)),
        accion)
    acciones = sorted(set(Auditoria.objects.values_list("accion", flat=True)))
    pagina = Paginator(registros, 50).get_page(request.GET.get("pagina"))
    return render(request, "reportes/auditoria.html", {
        "pagina": pagina, "desde": desde, "hasta": hasta, "accion": accion, "acciones": acciones})
