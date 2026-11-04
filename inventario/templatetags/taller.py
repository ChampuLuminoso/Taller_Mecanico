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
