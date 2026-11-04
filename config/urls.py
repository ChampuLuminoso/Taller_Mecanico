import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from inventario.urls import apartados_urls
from pedidos.urls import pedidos_urls, tienda_urls

# El admin de Django es la "puerta de emergencia" del Ingeniero.
# Su dirección se toma de una variable de entorno para no dejarla en /admin/, donde todos la buscan.
RUTA_ADMIN = os.environ.get("RUTA_ADMIN", "mantenimiento-tecnico/")

urlpatterns = [
    path(RUTA_ADMIN, admin.site.urls),
    path("cuenta/", include("cuentas.urls")),
    path("panel/inventario/", include("inventario.urls")),
    path("panel/apartados/", include(apartados_urls)),
    path("panel/", include("reportes.urls")),
    path("", include("citas.urls")),
    path("", include(pedidos_urls)),
    path("", include(tienda_urls)),   # la tienda es la página de inicio
]

if settings.DEBUG:   # en producción las imágenes las sirve el servidor web, no Django
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
