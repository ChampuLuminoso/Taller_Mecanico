from django.conf import settings

from .carrito import Carrito


def tienda(request):
    """Disponible en todas las plantillas: unidades del carrito, costo del envío y texto de entregas.
    Así el precio del domicilio se cambia en UN solo lugar (settings.TALLER)."""
    return {"unidades_carrito": len(Carrito(request)),
            "costo_envio": settings.TALLER["COSTO_ENVIO"],
            "texto_entregas": settings.TALLER["TEXTO_ENTREGAS"]}
