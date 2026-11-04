from django.urls import path

from . import views, views_apartados

app_name = "inventario"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.producto_form, name="nuevo"),
    path("plantilla.xlsx", views.plantilla, name="plantilla"),
    path("importar/", views.importar, name="importar"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/editar/", views.producto_form, name="editar"),
    path("<int:pk>/fila/", views.fila_editar, name="fila"),
    path("<int:pk>/entrada/", views.entrada, name="entrada"),
    path("<int:pk>/ajuste/", views.ajuste, name="ajuste"),
]

apartados_urls = ([
    path("", views_apartados.lista, name="lista"),
    path("solicitudes/", views_apartados.solicitudes, name="solicitudes"),
    path("solicitudes/<int:pk>/responder/", views_apartados.responder, name="responder"),
    path("nuevo/", views_apartados.nuevo, name="nuevo"),
    path("<int:pk>/cerrar/", views_apartados.cerrar, name="cerrar"),
], "apartados")
