from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("ventas/", views.ventas, name="ventas"),
    path("ventas/excel/", views.exportar, name="exportar"),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/<int:pk>/", views.cliente, name="cliente"),
    path("auditoria/", views.auditoria, name="auditoria"),
]
