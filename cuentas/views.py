from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import intentos, servicios
from .decoradores import ip_de, permiso_requerido
from .forms import BloqueoForm, PersonalForm, RegistroClienteForm
from .models import Usuario
from .permisos import CREAR_ROL, permisos_de, tiene_permiso


def _destino_seguro(request, por_defecto="cuentas:panel"):
    siguiente = request.POST.get("next") or request.GET.get("next")
    if siguiente and url_has_allowed_host_and_scheme(siguiente, {request.get_host()}, request.is_secure()):
        return siguiente
    return por_defecto


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect("cuentas:panel")
    error = None
    email = ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        ip = ip_de(request)
        if intentos.esta_frenado(email, ip):
            error = f"Demasiados intentos. Espera {intentos.MINUTOS_ESPERA} minutos e intenta de nuevo."
        else:
            usuario = authenticate(request, username=email, password=password)
            if usuario:
                intentos.limpiar(email, ip)
                login(request, usuario)   # Django cambia el id de sesión aquí (evita robo de sesión)
                if not request.POST.get("recordarme"):
                    request.session.set_expiry(0)   # se cierra al cerrar el navegador
                return redirect(_destino_seguro(request))
            intentos.registrar_fallo(email, ip)
            # Mismo mensaje para "no existe", "clave mala" o "bloqueado": no damos pistas.
            error = "Correo o contraseña incorrectos."
    return render(request, "cuentas/login.html", {"error": error, "email": email,
                                                  "next": request.GET.get("next", "")})


@require_POST
def cerrar_sesion(request):
    logout(request)
    messages.info(request, "Cerraste sesión.")
    return redirect("cuentas:login")


def registro(request):
    if request.user.is_authenticated:
        return redirect("cuentas:panel")
    form = RegistroClienteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            cliente = servicios.registrar_cliente(
                email=d["email"], password=d["password1"], nombres=d["nombres"], apellidos=d["apellidos"],
                telefono=d["telefono"], fecha_nacimiento=d["fecha_nacimiento"],
                acepta_marketing=d["acepta_marketing"], ip=ip_de(request),
            )
        except ValidationError as e:
            form.add_error(None, e)
        else:
            login(request, cliente.usuario, backend="cuentas.backends.BackendTaller")
            messages.success(request, f"¡Bienvenido, {cliente.nombres}! Tu cuenta quedó creada.")
            return redirect(_destino_seguro(request))
    return render(request, "cuentas/registro.html", {"form": form, "next": request.GET.get("next", "")})


@login_required
def panel(request):
    from inventario.models import Producto, SolicitudApartado

    permisos = permisos_de(request.user)
    # (nombre, permiso, nombre de URL o None si aún no existe, fase en la que llega)
    secciones = [
        ("Tienda", "tienda.comprar", "tienda:catalogo", ""),
        ("Mis pedidos", "tienda.comprar", "pedidos:mis_pedidos", ""),
        ("Mis citas", "citas.agendar_propia", "citas:mis_citas", ""),
        ("Inventario", "inventario.ver", "inventario:lista", ""),
        ("Pedidos de la tienda", "pedidos.gestionar", "pedidos:lista", ""),
        ("Solicitudes de apartado", "apartados.aprobar", "apartados:solicitudes", ""),
        ("Apartados", "apartados.gestionar", "apartados:lista", ""),
        ("Cargar productos desde Excel", "inventario.importar", "inventario:importar", ""),
        ("Agenda del taller", "citas.gestionar", "citas:agenda", ""),
        ("Bloquear días u horas", "agenda.bloquear", "citas:bloqueos", ""),
        ("Ventas (día, semana, mes)", "reportes.ver", "reportes:ventas", ""),
        ("Historial de clientes", "clientes.ver_historial", "reportes:clientes", ""),
        ("Personal", "personal.ver", "cuentas:personal", ""),
        ("Auditoría", "auditoria.ver", "reportes:auditoria", ""),
    ]
    contexto = {"secciones": [(n, url, fase) for n, perm, url, fase in secciones if perm in permisos]}
    if "inventario.ver" in permisos:
        contexto["bajo_stock"] = Producto.objects.bajo_stock_minimo()[:10]
    if "apartados.aprobar" in permisos:
        contexto["solicitudes_pendientes"] = SolicitudApartado.objects.filter(estado="PENDIENTE").count()
    if "reportes.ver" in permisos:
        from reportes.servicios import resumen
        contexto["ventas_hoy"] = resumen("dia", timezone.localdate())
    if "pedidos.gestionar" in permisos:
        from pedidos.models import Pedido
        contexto["pedidos_pendientes"] = Pedido.objects.filter(estado=Pedido.RECIBIDO).count()
    if "citas.gestionar" in permisos:
        from citas.models import Cita
        hoy = timezone.localdate()
        contexto["citas_hoy"] = Cita.objects.filter(estado__in=Cita.ACTIVAS, inicio__date=hoy).count()
    cliente = getattr(request.user, "cliente", None)
    if cliente and "citas.agendar_propia" in permisos:
        from citas.avisos import hora_co
        from citas.models import Cita
        proxima = cliente.citas.filter(estado__in=Cita.ACTIVAS, inicio__gte=timezone.now()) \
            .select_related("tipo_visita").order_by("inicio").first()
        if proxima:
            contexto["proxima_cita"] = proxima
            contexto["proxima_hora"] = hora_co(proxima.inicio)
    if "sistema.mantenimiento" in permisos:
        contexto["ruta_admin"] = reverse("admin:index")
    return render(request, "cuentas/panel.html", contexto)


@login_required
def cambiar_clave(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        update_session_auth_hash(request, usuario)   # no lo saca de la sesión actual
        messages.success(request, "Contraseña actualizada.")
        return redirect("cuentas:panel")
    return render(request, "cuentas/form_simple.html", {"form": form, "titulo": "Cambiar contraseña",
                                                         "boton": "Guardar contraseña"})


def politica(request):
    return render(request, "cuentas/politica.html")


# ───────────────────────── Personal ─────────────────────────

def _roles_que_puede_crear(usuario):
    return [rol for rol, permiso in CREAR_ROL.items() if tiene_permiso(usuario, permiso)]


@permiso_requerido("personal.ver")
def personal_lista(request):
    personal = (Usuario.objects.filter(empleado__isnull=False)   # .objects: Fran nunca aparece
                .select_related("empleado").prefetch_related("roles").order_by("empleado__nombres"))
    return render(request, "cuentas/personal_lista.html", {
        "personal": personal,
        "puede_crear": bool(_roles_que_puede_crear(request.user)),
        "puede_bloquear": tiene_permiso(request.user, "usuarios.gestionar"),
        "form_bloqueo": BloqueoForm(),
    })


@permiso_requerido("personal.crear_empleado")
def personal_crear(request):
    roles = _roles_que_puede_crear(request.user)
    form = PersonalForm(request.POST or None, roles_permitidos=roles)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            empleado = servicios.crear_personal(
                request.user, rol=d["rol"], email=d["email"], password=d["password1"],
                nombres=d["nombres"], apellidos=d["apellidos"], numero_documento=d["numero_documento"],
                telefono=d["telefono"], cargo=d["cargo"], hace_domicilios=d["hace_domicilios"],
                ip=ip_de(request),
            )
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, f"Cuenta creada para {empleado}.")
            return redirect("cuentas:personal")
    return render(request, "cuentas/form_simple.html", {"form": form, "titulo": "Nueva cuenta de personal",
                                                         "boton": "Crear cuenta"})


@require_POST
@permiso_requerido("usuarios.gestionar")
def personal_bloqueo(request, usuario_id):
    try:
        if request.POST.get("accion") == "desbloquear":
            u = servicios.desbloquear(request.user, usuario_id, ip=ip_de(request))
            messages.success(request, f"{u.nombre_visible} puede volver a entrar.")
        else:
            u = servicios.bloquear(request.user, usuario_id, request.POST.get("motivo", ""), ip=ip_de(request))
            messages.success(request, f"{u.nombre_visible} quedó bloqueado.")
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, " ".join(getattr(e, "messages", [str(e)])))
    except Usuario.DoesNotExist:
        messages.error(request, "Ese usuario no existe.")
    return redirect("cuentas:personal")
