from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from cuentas.decoradores import permiso_requerido
from cuentas.models import Vehiculo
from cuentas.permisos import permisos_de, tiene_permiso
from cuentas.servicios import buscar_cliente

from . import servicios
from .avisos import hora_co
from .calendario import info_dia
from .forms import BloqueoForm, CancelarForm, ReservaForm
from .models import Bahia, BloqueoAgenda, Cita, ExcepcionCalendario, TipoVisita


def _texto_error(e):
    return " ".join(getattr(e, "messages", [str(e)]))


def _fecha(valor):
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _cliente_de(usuario):
    return getattr(usuario, "cliente", None) if tiene_permiso(usuario, "citas.agendar_propia") else None


def _puede_usar_agenda(usuario):
    return servicios.es_personal(usuario) or _cliente_de(usuario) is not None


# ───────────────────────── Calendario y reserva ─────────────────────────

def _contexto_calendario(request, tipo, fecha, personal, cita=None):
    dias = servicios.dias_para_calendario(tipo, personal, excluir_cita=cita) if tipo else []
    # La grilla empieza el lunes de esta semana para que los días caigan en su columna.
    relleno = dias[0]["fecha"].weekday() if dias else 0
    horas = servicios.franjas_libres(fecha, tipo, personal, excluir_cita=cita) if (tipo and fecha) else []
    return {"tipos": TipoVisita.objects.filter(activo=True), "tipo": tipo, "dias": dias, "relleno": range(relleno),
            "fecha": fecha, "info_fecha": info_dia(fecha) if fecha else None,
            "horas": [(h, hora_co(h)) for h in horas], "cita": cita}


@login_required
def horas(request):
    """Fragmento HTMX: horas libres del día que se tocó en el calendario."""
    if not _puede_usar_agenda(request.user):
        raise PermissionDenied
    tipo = TipoVisita.objects.filter(activo=True, pk=request.GET.get("tipo") or 0).first()
    cita = None
    if request.GET.get("cita"):
        cita = _cita_propia_o_404(request.user, request.GET["cita"])
    ctx = _contexto_calendario(request, tipo, _fecha(request.GET.get("fecha")), servicios.es_personal(request.user), cita)
    return render(request, "citas/_horas.html", ctx)


def _vehiculo(cliente, d):
    if d.get("vehiculo"):
        return d["vehiculo"]
    existente = Vehiculo.objects.filter(placa=d["placa"]).first()
    if existente and existente.cliente_id != cliente.pk:
        raise ValidationError("Esa placa está registrada con otro cliente. Comunícate con el taller.")
    if existente:
        return existente
    return Vehiculo.objects.create(cliente=cliente, placa=d["placa"], marca=d["marca"].strip(),
                                   modelo=d["modelo"].strip(), anio=d["anio"])


@login_required
def agendar(request):
    personal = servicios.es_personal(request.user)
    cliente = None if personal else _cliente_de(request.user)
    if not personal and cliente is None:
        raise PermissionDenied

    datos = request.POST or None
    tipo = TipoVisita.objects.filter(activo=True, pk=(datos or request.GET).get("tipo") or 0).first()
    fecha = _fecha((datos or request.GET).get("fecha"))
    form = ReservaForm(datos, cliente=cliente, para_personal=personal,
                       initial={"tipo": tipo, "fecha": fecha})

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        destinatario = cliente
        if personal:
            destinatario, error = buscar_cliente(d["cliente"])
            if error:
                form.add_error("cliente", error)
        if destinatario:
            inicio = timezone.make_aware(datetime.combine(d["fecha"], d["hora"]))
            try:
                with transaction.atomic():   # si la cita falla, tampoco se guarda el vehículo nuevo
                    cita = servicios.agendar(destinatario, d["tipo"], inicio, request.user,
                                             vehiculo=_vehiculo(destinatario, d), nota=d["nota"])
            except (ValidationError, PermissionDenied) as e:
                form.add_error(None, _texto_error(e))
            else:
                messages.success(request, f"Cita confirmada: {d['tipo'].nombre}, "
                                          f"{timezone.localtime(cita.inicio):%d/%m/%Y} a las {hora_co(cita.inicio)}.")
                if personal:
                    return redirect(f"{_url_agenda()}?fecha={d['fecha']:%Y-%m-%d}")
                return redirect("citas:mis_citas")

    ctx = _contexto_calendario(request, tipo, fecha, personal)
    ctx.update({"form": form, "personal": personal,
                "hora_elegida": (datos or {}).get("hora", ""), "accion": "agendar"})
    return render(request, "citas/agendar.html", ctx)


def _url_agenda():
    return reverse("citas:agenda")


# ───────────────────────── Mis citas (cliente) ─────────────────────────

def _cita_propia_o_404(usuario, pk):
    cita = get_object_or_404(Cita.objects.select_related("cliente", "tipo_visita", "vehiculo"), pk=pk)
    if not servicios.es_personal(usuario) and cita.cliente != _cliente_de(usuario):
        raise Http404   # no revelamos que la cita existe
    return cita


@permiso_requerido("citas.agendar_propia")
def mis_citas(request):
    cliente = _cliente_de(request.user)
    if cliente is None:
        raise PermissionDenied
    ahora = timezone.now()
    base = cliente.citas.select_related("tipo_visita", "vehiculo")
    proximas = list(base.filter(estado__in=Cita.ACTIVAS, fin__gte=ahora).order_by("inicio"))
    for c in proximas:
        c.se_puede_cambiar = servicios.puede_cambiar(c, request.user, ahora)
        c.hora_texto = hora_co(c.inicio)
    anteriores = base.exclude(pk__in=[c.pk for c in proximas]).order_by("-inicio")[:10]
    return render(request, "citas/mis_citas.html", {
        "proximas": proximas, "anteriores": anteriores,
        "limite": servicios.CFG["CITAS_LIMITE_CAMBIO_HORAS"]})


@require_POST
@login_required
def cancelar(request, pk):
    cita = _cita_propia_o_404(request.user, pk)
    form = CancelarForm(request.POST)
    motivo = form.cleaned_data["motivo"] if form.is_valid() else ""
    try:
        servicios.cancelar(cita.pk, request.user, motivo)
        messages.success(request, "La cita quedó cancelada.")
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, _texto_error(e))
    if servicios.es_personal(request.user):
        return redirect(f"{_url_agenda()}?fecha={timezone.localtime(cita.inicio):%Y-%m-%d}")
    return redirect("citas:mis_citas")


@login_required
def reprogramar(request, pk):
    cita = _cita_propia_o_404(request.user, pk)
    personal = servicios.es_personal(request.user)
    if not servicios.puede_cambiar(cita, request.user):
        messages.error(request, f"Ya no se puede cambiar esta cita por la web (límite: "
                                f"{servicios.CFG['CITAS_LIMITE_CAMBIO_HORAS']} horas antes). Comunícate con el taller.")
        return redirect("citas:mis_citas" if not personal else "citas:agenda")

    fecha = _fecha(request.POST.get("fecha") or request.GET.get("fecha"))
    if request.method == "POST":
        try:
            hora = datetime.strptime(request.POST.get("hora", ""), "%H:%M").time()
            nuevo = timezone.make_aware(datetime.combine(fecha, hora))
            servicios.reprogramar(cita.pk, request.user, nuevo)
        except (ValueError, TypeError):
            messages.error(request, "Elige un día y una hora del calendario.")
        except (ValidationError, PermissionDenied) as e:
            messages.error(request, _texto_error(e))
        else:
            messages.success(request, f"Listo: tu cita quedó para el {nuevo:%d/%m/%Y} a las {hora_co(nuevo)}.")
            if personal:
                return redirect(f"{_url_agenda()}?fecha={fecha:%Y-%m-%d}")
            return redirect("citas:mis_citas")

    ctx = _contexto_calendario(request, cita.tipo_visita, fecha, personal, cita)
    ctx.update({"accion": "reprogramar", "personal": personal, "hora_actual": hora_co(cita.inicio)})
    return render(request, "citas/agendar.html", ctx)


# ───────────────────────── Agenda del taller (personal) ─────────────────────────

@permiso_requerido("citas.gestionar")
def agenda(request):
    fecha = _fecha(request.GET.get("fecha")) or timezone.localdate()
    inicio = timezone.make_aware(datetime.combine(fecha, datetime.min.time()))
    fin = inicio + timedelta(days=1)
    citas = list(Cita.objects.filter(inicio__gte=inicio, inicio__lt=fin)
                 .select_related("cliente", "vehiculo", "tipo_visita", "bahia", "creada_por")
                 .order_by("inicio", "bahia__nombre"))
    hoy = timezone.localdate()
    for c in citas:
        c.hora_texto, c.fin_texto = hora_co(c.inicio), hora_co(c.fin)
        c.se_puede_cerrar = c.estado in Cita.ACTIVAS and fecha <= hoy
        c.se_puede_cambiar = servicios.puede_cambiar(c, request.user)
    bloqueos = BloqueoAgenda.objects.filter(inicio__lt=fin, fin__gt=inicio).select_related("bahia")
    activas = [c for c in citas if c.estado in Cita.ACTIVAS]
    return render(request, "citas/agenda.html", {
        "fecha": fecha, "info": info_dia(fecha), "citas": citas, "bloqueos": bloqueos,
        "anterior": fecha - timedelta(days=1), "siguiente": fecha + timedelta(days=1), "hoy": hoy,
        "bahias": Bahia.objects.filter(activa=True), "total_activas": len(activas),
        "permisos": permisos_de(request.user), "form_cancelar": CancelarForm()})


@require_POST
@permiso_requerido("citas.gestionar")
def marcar(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    try:
        servicios.marcar(pk, request.user, request.POST.get("estado"))
    except ValidationError as e:
        messages.error(request, _texto_error(e))
    return redirect(f"{_url_agenda()}?fecha={timezone.localtime(cita.inicio):%Y-%m-%d}")


@permiso_requerido("agenda.bloquear")
def bloqueos(request):
    form = BloqueoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            _, afectadas = servicios.bloquear(request.user, d["fecha"], d["motivo"], d["desde"], d["hasta"])
        except ValidationError as e:
            form.add_error(None, _texto_error(e))
        else:
            messages.success(request, "Bloqueo guardado. Los clientes ya no podrán agendar en ese horario.")
            if afectadas:
                lista = "; ".join(f"{c.cliente} ({hora_co(c.inicio)}, cel. {c.cliente.telefono})" for c in afectadas)
                messages.info(request, f"Ojo: ya había {len(afectadas)} cita(s) en ese horario y siguen activas. "
                                       f"Avísales y cancélalas desde la agenda: {lista}")
            return redirect("citas:bloqueos")
    hoy = timezone.localdate()
    return render(request, "citas/bloqueos.html", {
        "form": form,
        "dias": ExcepcionCalendario.objects.filter(fecha__gte=hoy).select_related("creado_por"),
        "horas": BloqueoAgenda.objects.filter(fin__gte=timezone.now()).order_by("inicio").select_related("creado_por"),
    })


@require_POST
@permiso_requerido("agenda.bloquear")
def quitar_bloqueo(request, tipo, pk):
    try:
        servicios.quitar_bloqueo(request.user, tipo, pk)
        messages.success(request, "Bloqueo eliminado: ese horario vuelve a estar disponible.")
    except (ValidationError, ExcepcionCalendario.DoesNotExist, BloqueoAgenda.DoesNotExist):
        messages.error(request, "No se encontró ese bloqueo.")
    return redirect("citas:bloqueos")
