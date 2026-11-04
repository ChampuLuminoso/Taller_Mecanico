"""Envío de correos del sistema. Un fallo de correo NUNCA debe tumbar la operación que lo causó."""
import logging

from django.conf import settings
from django.core.mail import EmailMessage

from .models import Usuario
from .permisos import tiene_permiso

log = logging.getLogger(__name__)


def correos_con_permiso(permiso):
    """Correos de quienes tienen un permiso (Fran incluido), sin cuentas bloqueadas ni eliminadas."""
    activos = Usuario.todos.filter(is_active=True, bloqueado=False, eliminado_en__isnull=True)
    return [u.email for u in activos if tiene_permiso(u, permiso)]


def enviar(asunto, cuerpo, *, para=(), copia_oculta=()):
    """Copia oculta: cada destinatario recibe el correo sin ver a los demás (así Fran no se delata)."""
    para, copia_oculta = list(filter(None, para)), list(filter(None, copia_oculta))
    if not para and not copia_oculta:
        return False
    try:
        EmailMessage(subject=f"[{settings.MARCA['NOMBRE']}] {asunto}", body=cuerpo,
                     from_email=settings.DEFAULT_FROM_EMAIL,
                     to=para or [settings.DEFAULT_FROM_EMAIL], bcc=copia_oculta,
                     # Si el cliente responde, la respuesta llega al correo del taller (no a "avisos@").
                     reply_to=[settings.CORREO_RESPUESTA] if settings.CORREO_RESPUESTA else None).send()
        return True
    except Exception:
        log.exception("No se pudo enviar el correo: %s", asunto)
        return False
