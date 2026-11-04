from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("entrar/", views.iniciar_sesion, name="login"),
    path("salir/", views.cerrar_sesion, name="logout"),
    path("registro/", views.registro, name="registro"),
    path("panel/", views.panel, name="panel"),
    path("clave/", views.cambiar_clave, name="cambiar_clave"),
    path("privacidad/", views.politica, name="politica"),
    path("personal/", views.personal_lista, name="personal"),
    path("personal/nuevo/", views.personal_crear, name="personal_crear"),
    path("personal/<int:usuario_id>/bloqueo/", views.personal_bloqueo, name="personal_bloqueo"),
]
