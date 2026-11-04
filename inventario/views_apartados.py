from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.decoradores import permiso_requerido
from cuentas.servicios import buscar_cliente
from cuentas.permisos import permisos_de

from . import servicios
from .forms import ApartadoDirectoForm, ResponderSolicitudForm
from .models import Apartado, Producto, SolicitudApartado


def _error(request, e):
    messages.error(request, " ".join(getattr(e, "messages", [str(e)])))


@permiso_requerido("apartados.aprobar")
def solicitudes(request):
    pendientes = (SolicitudApartado.objects.filter(estado=SolicitudApartado.PENDIENTE)
                  .select_related("cliente", "producto"))
    recientes = (SolicitudApartado.objects.exclude(estado=SolicitudApartado.PENDIENTE)
                 .select_related("cliente", "producto", "revisada_por").order_by("-revisada_en")[:15])
    return render(request, "apartados/solicitudes.html", {
        "pendientes": pendientes, "recientes": recientes, "form": ResponderSolicitudForm()})


@require_POST
@permiso_requerido("apartados.aprobar")
def responder(request, pk):
    form = ResponderSolicitudForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa el abono.")
        return redirect("apartados:solicitudes")
    aprobar = request.POST.get("decision") == "aprobar"
    try:
        servicios.responder_solicitud(pk, request.user, aprobar=aprobar,
                                      respuesta=form.cleaned_data["respuesta"],
                                      abono=form.cleaned_data["abono"] or 0)
        messages.success(request, "Solicitud aprobada: el producto quedó apartado." if aprobar
                         else "Solicitud rechazada.")
    except (ValidationError, PermissionDenied) as e:
        _error(request, e)
    return redirect("apartados:solicitudes")


@permiso_requerido("apartados.gestionar")
def lista(request):
    estado = request.GET.get("estado", Apartado.ACTIVO)
    apartados = Apartado.objects.select_related("cliente", "producto", "creado_por__empleado")
    if estado in dict(Apartado.ESTADOS):
        apartados = apartados.filter(estado=estado)
    apartados = apartados.order_by("vence_en" if estado == Apartado.ACTIVO else "-cerrado_en")[:200]
    return render(request, "apartados/lista.html", {
        "apartados": apartados, "estado": estado, "estados": Apartado.ESTADOS,
        "permisos": permisos_de(request.user)})


@require_POST
@permiso_requerido("apartados.gestionar")
def cerrar(request, pk):
    nuevo = request.POST.get("estado")
    try:
        if nuevo not in (Apartado.ENTREGADO, Apartado.CANCELADO):
            raise ValidationError("Acción inválida.")
        servicios.cerrar_apartado(pk, request.user, nuevo, request.POST.get("motivo", "").strip())
        messages.success(request, "Apartado entregado." if nuevo == Apartado.ENTREGADO
                         else "Apartado cancelado: las unidades volvieron a estar disponibles.")
    except (ValidationError, PermissionDenied) as e:
        _error(request, e)
    return redirect("apartados:lista")


@permiso_requerido("apartados.aprobar")
def nuevo(request):
    """Apartado directo: el cliente llamó o vino al taller."""
    form = ApartadoDirectoForm(request.POST or None, initial={"sku": request.GET.get("sku", "")})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        producto = Producto.objects.filter(sku=d["sku"].upper().strip(), activo=True).first()
        cliente, error_cliente = buscar_cliente(d["cliente"])
        if not producto:
            form.add_error("sku", "No existe un producto activo con ese ProductoID.")
        elif error_cliente:
            form.add_error("cliente", error_cliente)
        else:
            try:
                apartado = servicios.crear_apartado(producto, cliente, d["cantidad"], request.user,
                                                    abono=d["abono"] or 0, nota=d["nota"])
            except (ValidationError, PermissionDenied) as e:
                form.add_error(None, e)
            else:
                messages.success(request, f"Apartado para {cliente} hasta el "
                                          f"{timezone.localtime(apartado.vence_en):%d/%m/%Y %I:%M %p}.")
                return redirect("apartados:lista")
    return render(request, "apartados/nuevo.html", {"form": form})
