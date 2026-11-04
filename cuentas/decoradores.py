from functools import wraps

from django.contrib.auth.decorators import login_required

from .permisos import requiere_permiso


def permiso_requerido(permiso):
    """@permiso_requerido("personal.ver") encima de una vista:
    sin sesión → al login; con sesión pero sin permiso → error 403."""
    def decorador(vista):
        @login_required
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            requiere_permiso(request.user, permiso)
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


def ip_de(request):
    # Detrás de un proxy (en producción) habrá que leer X-Forwarded-For de forma segura.
    return request.META.get("REMOTE_ADDR")
