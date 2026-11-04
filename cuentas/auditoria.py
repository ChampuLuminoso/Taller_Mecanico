"""Un solo punto para registrar auditoría. Decide en qué tabla va cada acción."""
from .models import Auditoria, AuditoriaFran, Usuario


def registrar(usuario, accion, entidad, entidad_id="", antes=None, despues=None, ip=None):
    tabla = AuditoriaFran if (usuario and usuario.es_fran) else Auditoria
    return tabla.objects.create(
        usuario=usuario, accion=accion, entidad=entidad, entidad_id=str(entidad_id),
        antes=antes, despues=despues, ip=ip,
    )


def auditoria_para(usuario, desde=None, hasta=None, accion=""):
    """Lo que cada quien puede leer:
    - Jefe: la auditoría general (todos menos Fran).
    - Fran: absolutamente todo, en una sola línea de tiempo."""
    from .permisos import requiere_permiso, tiene_permiso

    requiere_permiso(usuario, "auditoria.ver")

    def filtrar(qs):
        if desde:
            qs = qs.filter(creado_en__gte=desde)
        if hasta:
            qs = qs.filter(creado_en__lt=hasta)
        if accion:
            qs = qs.filter(accion=accion)
        return list(qs.select_related("usuario")[:1000])

    registros = filtrar(Auditoria.objects.all())
    if tiene_permiso(usuario, "auditoria.ver_total"):
        registros += filtrar(AuditoriaFran.objects.all())
    return sorted(registros, key=lambda r: r.creado_en, reverse=True)


def crear_fran(email, password):
    """Se ejecuta UNA vez, desde la consola del servidor (nunca desde la web)."""
    return Usuario.todos.create_user(email=email, password=password, es_fran=True)
