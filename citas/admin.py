from django.contrib import admin

from .models import Bahia, BloqueoAgenda, Cita, ExcepcionCalendario, HorarioTaller, TipoVisita


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ["inicio", "cliente", "tipo_visita", "bahia", "estado"]
    list_filter = ["estado", "tipo_visita", "bahia"]
    date_hierarchy = "inicio"


@admin.register(HorarioTaller)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ["dia_semana", "abierto", "abre", "cierra"]
    list_editable = ["abierto", "abre", "cierra"]


admin.site.register([TipoVisita, Bahia, ExcepcionCalendario, BloqueoAgenda])
