from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def pesos(valor):
    """85000 → $85.000 (formato colombiano, sin centavos)."""
    if valor in (None, ""):
        return ""
    entero = int(Decimal(valor).quantize(Decimal("1")))
    return "$" + f"{entero:,}".replace(",", ".")


@register.filter
def whatsapp(telefono):
    """3001234567 → 573001234567, para armar enlaces wa.me."""
    digitos = "".join(c for c in str(telefono or "") if c.isdigit())
    return digitos if digitos.startswith("57") else f"57{digitos}"


@register.filter
def hora(valor):
    """8:00 a. m. / 2:30 p. m. — acepta una hora (time) o una fecha con hora (en hora de Bogotá)."""
    from datetime import datetime

    from django.utils import timezone
    if valor in (None, ""):
        return ""
    if isinstance(valor, datetime):
        valor = timezone.localtime(valor) if timezone.is_aware(valor) else valor
    return f"{valor.hour % 12 or 12}:{valor.minute:02d} {'a. m.' if valor.hour < 12 else 'p. m.'}"
