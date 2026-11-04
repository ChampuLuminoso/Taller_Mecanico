"""
Operaciones sobre cuentas. Cada una valida permisos en el servidor y deja auditoría.
Las vistas solo reciben datos del formulario y llaman aquí.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .auditoria import registrar
from .models import Cliente, Empleado, Rol, Usuario, UsuarioRol
from .permisos import CREAR_ROL, rango_de, requiere_permiso


def correo_libre(email: str) -> bool:
    # Se revisa en `todos` para no chocar con el correo de Fran.
    return not Usuario.todos.filter(email__iexact=email).exists()


@transaction.atomic
def registrar_cliente(*, email, password, nombres, apellidos, telefono, fecha_nacimiento,
                      acepta_marketing=False, ip=None):
    """Registro público desde la web. La edad ya viene validada por el formulario,
    pero se vuelve a validar aquí con full_clean() (nunca confiar solo en el navegador)."""
    if not correo_libre(email):
        raise ValidationError({"email": "Ya existe una cuenta con ese correo."})
    usuario = Usuario.todos.create_user(email=email, password=password)
    UsuarioRol.objects.create(usuario=usuario, rol=Rol.objects.get(codigo=Rol.CLIENTE))
    cliente = Cliente(
        usuario=usuario, nombres=nombres.strip(), apellidos=apellidos.strip(), telefono=telefono,
        email=usuario.email, fecha_nacimiento=fecha_nacimiento, acepta_marketing=acepta_marketing,
        acepta_datos_en=timezone.now(), version_politica=settings.TALLER["VERSION_POLITICA"],
    )
    cliente.full_clean(exclude=["usuario"])
    cliente.save()
    registrar(usuario, "registro_cliente", "Usuario", usuario.pk, despues={"email": usuario.email}, ip=ip)
    return cliente


@transaction.atomic
def crear_personal(creador, *, rol, email, password, nombres, apellidos, numero_documento,
                   telefono, cargo, hace_domicilios=False, ip=None):
    if rol not in CREAR_ROL:
        raise PermissionDenied("Ese rol no se crea desde la web.")
    requiere_permiso(creador, CREAR_ROL[rol])
    if not correo_libre(email):
        raise ValidationError({"email": "Ya existe una cuenta con ese correo."})
    if Empleado.objects.filter(numero_documento=numero_documento).exists():
        raise ValidationError({"numero_documento": "Ya hay un empleado con ese documento."})

    usuario = Usuario.todos.create_user(email=email, password=password)
    UsuarioRol.objects.create(usuario=usuario, rol=Rol.objects.get(codigo=rol), asignado_por=creador)
    empleado = Empleado(usuario=usuario, nombres=nombres.strip(), apellidos=apellidos.strip(),
                        numero_documento=numero_documento, telefono=telefono, cargo=cargo,
                        hace_domicilios=hace_domicilios)
    empleado.full_clean(exclude=["usuario"])
    empleado.save()
    registrar(creador, "crear_personal", "Usuario", usuario.pk,
              despues={"email": usuario.email, "rol": rol, "cargo": cargo}, ip=ip)
    return empleado


def _puede_actuar_sobre(actor, objetivo):
    requiere_permiso(actor, "usuarios.gestionar")
    if actor.pk == objetivo.pk:
        raise PermissionDenied("No puedes bloquearte a ti mismo.")
    if rango_de(objetivo) >= rango_de(actor):
        raise PermissionDenied("Solo puedes gestionar cuentas de rango menor al tuyo.")


@transaction.atomic
def bloquear(actor, objetivo_id, motivo, ip=None):
    if not motivo or not motivo.strip():
        raise ValidationError("Escribe el motivo del bloqueo.")
    objetivo = Usuario.objects.select_for_update().get(pk=objetivo_id)  # Fran no está aquí: no se puede bloquear
    _puede_actuar_sobre(actor, objetivo)
    objetivo.bloqueado, objetivo.motivo_bloqueo = True, motivo.strip()
    objetivo.save(update_fields=["bloqueado", "motivo_bloqueo"])
    registrar(actor, "bloquear_usuario", "Usuario", objetivo.pk, despues={"motivo": motivo}, ip=ip)
    return objetivo


@transaction.atomic
def desbloquear(actor, objetivo_id, ip=None):
    objetivo = Usuario.objects.select_for_update().get(pk=objetivo_id)
    _puede_actuar_sobre(actor, objetivo)
    antes = objetivo.motivo_bloqueo
    objetivo.bloqueado, objetivo.motivo_bloqueo = False, ""
    objetivo.save(update_fields=["bloqueado", "motivo_bloqueo"])
    registrar(actor, "desbloquear_usuario", "Usuario", objetivo.pk, antes={"motivo": antes}, ip=ip)
    return objetivo


def buscar_cliente(texto):
    """Busca un cliente activo por celular (últimos 10 dígitos) o cédula.
    Devuelve (cliente, None) o (None, mensaje de error). Lo usan apartados y citas."""
    from django.db.models import Q

    buscar = "".join(c for c in (texto or "") if c.isalnum())
    if len(buscar) < 5:
        return None, "Escribe el celular o la cédula completos."
    clientes = list(Cliente.objects.filter(anonimizado_en__isnull=True)
                    .filter(Q(telefono__endswith=buscar[-10:]) | Q(numero_documento=buscar))[:2])
    if not clientes:
        return None, "No encontramos ese cliente. Pídele que se registre en la web."
    if len(clientes) > 1:
        return None, "Hay varios clientes con ese dato. Usa la cédula."
    return clientes[0], None
