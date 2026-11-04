"""Aviso de stock mínimo por correo a quienes tienen el permiso (Jefes y Fran)."""
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse

from cuentas.models import Usuario
from cuentas.permisos import tiene_permiso

from .models import Producto

log = logging.getLogger(__name__)


def destinatarios():
    return [u.email for u in Usuario.todos.filter(is_active=True, bloqueado=False, eliminado_en__isnull=True)
            if tiene_permiso(u, "inventario.alertas_correo")]


def avisar_stock_minimo(producto_id):
    producto = Producto.objects.get(pk=producto_id)
    para = destinatarios()
    if not para:
        return 0
    url = settings.TALLER["URL_SITIO"].rstrip("/") + reverse("inventario:detalle", args=[producto.pk])
    estado = "SE AGOTÓ" if producto.disponible == 0 else f"quedan {producto.disponible}"
    try:
        # bcc: cada jefe recibe el correo sin ver a los demás destinatarios (Fran incluido).
        EmailMessage(
            subject=f"[Taller Francois] Stock bajo: {producto.nombre} ({estado})",
            body=(f"El producto {producto.sku} · {producto.nombre} llegó a su stock mínimo.\n\n"
                  f"Disponibles: {producto.disponible}\n"
                  f"Apartados: {producto.cantidad_apartada}\n"
                  f"Stock mínimo: {producto.stock_minimo}\n\n"
                  f"Ver producto: {url}\n"),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.DEFAULT_FROM_EMAIL],
            bcc=para,
        ).send()
    except Exception:   # un fallo de correo nunca debe tumbar una venta
        log.exception("No se pudo enviar la alerta de stock de %s", producto.sku)
        return 0
    return len(para)
