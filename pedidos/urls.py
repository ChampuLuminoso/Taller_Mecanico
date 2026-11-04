from django.urls import path

from . import views, views_tienda

tienda_urls = ([
    path("", views_tienda.catalogo, name="catalogo"),
    path("tienda/p/<str:sku>/", views_tienda.producto, name="producto"),
    path("tienda/p/<str:sku>/apartar/", views_tienda.solicitar_apartado, name="apartar"),
    path("carrito/", views_tienda.carrito, name="carrito"),
    path("carrito/agregar/<int:producto_id>/", views_tienda.carrito_agregar, name="agregar"),
    path("carrito/cambiar/<int:producto_id>/", views_tienda.carrito_cambiar, name="cambiar"),
    path("comprar/", views_tienda.comprar, name="comprar"),
], "tienda")

pedidos_urls = ([
    path("mis-pedidos/", views_tienda.mis_pedidos, name="mis_pedidos"),
    path("mis-pedidos/<int:pk>/cancelar/", views_tienda.cancelar_mio, name="cancelar_mio"),
    path("panel/pedidos/", views.lista, name="lista"),
    path("panel/pedidos/<int:pk>/", views.detalle, name="detalle_taller"),
    path("panel/pedidos/<int:pk>/accion/", views.accion, name="accion"),
], "pedidos")
