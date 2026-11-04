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
    """IP real del cliente. Detrás de Railway, REMOTE_ADDR es la del proxy y la real viene en
    X-Forwarded-For. Se toma la que agregó NUESTRO proxy (contando desde la derecha), porque las
    de la izquierda las puede inventar cualquiera que mande esa cabecera."""
    from django.conf import settings

    saltos = getattr(settings, "PROXIES_DE_CONFIANZA", 0)
    cadena = [ip.strip() for ip in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if ip.strip()]
    if saltos and len(cadena) >= saltos:
        return cadena[-saltos]
    return request.META.get("REMOTE_ADDR")
