"""Panel de pedidos del taller."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cuentas.decoradores import permiso_requerido
from cuentas.permisos import permisos_de

from . import servicios
from .models import Pedido

P = Pedido
FILTROS = [("pendientes", "Por confirmar", [P.RECIBIDO]),
           ("en_proceso", "En proceso", [P.CONFIRMADO, P.ALISTADO, P.EN_CAMINO]),
           ("entregados", "Entregados", [P.ENTREGADO]),
           ("cancelados", "Cancelados", [P.CANCELADO])]


@permiso_requerido("pedidos.gestionar")
def lista(request):
    filtro = request.GET.get("ver", "pendientes")
    estados = dict((k, e) for k, _, e in FILTROS).get(filtro, [P.RECIBIDO])
    pedidos = (Pedido.objects.filter(estado__in=estados).select_related("cliente", "repartidor")
               .prefetch_related("items").order_by("creado_en" if filtro != "entregados" else "-entregado_en")[:100])
    conteos = {k: Pedido.objects.filter(estado__in=e).count() for k, _, e in FILTROS[:2]}
    return render(request, "pedidos/lista.html", {
        "pedidos": pedidos, "filtro": filtro, "filtros": [(k, n) for k, n, _ in FILTROS], "conteos": conteos})


def _acciones(pedido, permisos):
    """Qué botones ve cada quien según el estado. El servidor vuelve a validar al pulsarlos."""
    a = []
    if pedido.estado == P.RECIBIDO and "pedidos.confirmar" in permisos:
        a.append(("confirmar", "Confirmar y descontar inventario", ""))
    if pedido.estado == P.CONFIRMADO and "pedidos.gestionar" in permisos:
        a.append(("ALISTADO", "Marcar alistado", "secundario"))
    if pedido.modalidad == P.ENVIO and pedido.estado in (P.CONFIRMADO, P.ALISTADO) and "pedidos.gestionar" in permisos:
        a.append(("EN_CAMINO", "Salió a entrega", ""))
    entregable = [P.EN_CAMINO] if pedido.modalidad == P.ENVIO else [P.CONFIRMADO, P.ALISTADO]
    if pedido.estado in entregable and "pedidos.entregar" in permisos:
        a.append(("ENTREGADO", "Entregado y pagado", ""))
    return a


@permiso_requerido("pedidos.gestionar")
def detalle(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related("cliente", "repartidor", "confirmado_por",
                                                             "cancelado_por"), pk=pk)
    permisos = permisos_de(request.user)
    items = list(pedido.items.select_related("producto"))
    return render(request, "pedidos/detalle.html", {
        "p": pedido, "items": items, "acciones": _acciones(pedido, permisos),
        "puede_cancelar": "pedidos.confirmar" in permisos and pedido.estado not in (P.ENTREGADO, P.CANCELADO),
        "falta_stock": pedido.estado == P.RECIBIDO and any(i.cantidad > i.producto.disponible for i in items)})


@require_POST
@permiso_requerido("pedidos.gestionar")
def accion(request, pk):
    paso = request.POST.get("accion", "")
    try:
        if paso == "confirmar":
            servicios.confirmar(pk, request.user)
            messages.success(request, "Pedido confirmado: el inventario quedó descontado.")
        elif paso == "cancelar":
            servicios.cancelar(pk, request.user, request.POST.get("motivo", ""))
            messages.success(request, "Pedido cancelado. Si ya se había descontado, volvió al inventario.")
        else:
            servicios.avanzar(pk, request.user, paso)
            messages.success(request, "Pedido actualizado.")
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, " ".join(getattr(e, "messages", [str(e)])))
    except Pedido.DoesNotExist:
        messages.error(request, "Ese pedido no existe.")
    return redirect("pedidos:detalle_taller", pk=pk)
