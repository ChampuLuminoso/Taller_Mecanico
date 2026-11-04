import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_control
from django.views.static import serve

from inventario.urls import apartados_urls
from pedidos.urls import pedidos_urls, tienda_urls

# El admin de Django es la "puerta de emergencia" del Ingeniero.
# Su dirección se toma de una variable de entorno para no dejarla en /admin/, donde todos la buscan.
RUTA_ADMIN = os.environ.get("RUTA_ADMIN", "mantenimiento-tecnico/")


def salud(request):
    """Railway entra aquí cada vez que publica, para saber si el sitio quedó vivo (incluida la base de datos)."""
    with connection.cursor() as c:
        c.execute("SELECT 1")
    return HttpResponse("ok", content_type="text/plain")


@cache_control(public=True, max_age=60 * 60 * 24 * 7)
def fotos(request, path, document_root):
    return serve(request, path, document_root=document_root)


urlpatterns = [
    path("salud/", salud),
    path(RUTA_ADMIN, admin.site.urls),
    path("cuenta/", include("cuentas.urls")),
    path("panel/inventario/", include("inventario.urls")),
    path("panel/apartados/", include(apartados_urls)),
    path("panel/", include("reportes.urls")),
    path("", include("citas.urls")),
    path("", include(pedidos_urls)),
    path("", include(tienda_urls)),   # la tienda es la página de inicio
]

# Fotos de productos. WhiteNoise solo sirve archivos que existen al publicar; las fotos que sube el Jefe
# llegan después, así que las sirve Django desde el volumen. Para el tráfico de un taller es suficiente.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", fotos, {"document_root": settings.MEDIA_ROOT})]
