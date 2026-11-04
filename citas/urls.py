from django.urls import path

from . import views

app_name = "citas"

urlpatterns = [
    # Clientes
    path("citas/", views.mis_citas, name="mis_citas"),
    path("citas/agendar/", views.agendar, name="agendar"),
    path("citas/agendar/horas/", views.horas, name="horas"),
    path("citas/<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("citas/<int:pk>/cambiar/", views.reprogramar, name="reprogramar"),
    # Taller
    path("panel/agenda/", views.agenda, name="agenda"),
    path("panel/agenda/<int:pk>/estado/", views.marcar, name="marcar"),
    path("panel/agenda/bloqueos/", views.bloqueos, name="bloqueos"),
    path("panel/agenda/bloqueos/<str:tipo>/<int:pk>/quitar/", views.quitar_bloqueo, name="quitar_bloqueo"),
]
