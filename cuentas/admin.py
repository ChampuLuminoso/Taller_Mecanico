from django.contrib import admin

from .models import Auditoria, Cliente, Direccion, Empleado, Rol, Usuario, UsuarioRol, Vehiculo

# Nota: el admin usa Usuario.objects, que ya excluye a Fran. AuditoriaFran no se registra.


class UsuarioRolInline(admin.TabularInline):
    model = UsuarioRol
    fk_name = "usuario"
    extra = 0
    readonly_fields = ["asignado_por", "asignado_en"]


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ["email", "is_active", "bloqueado", "eliminado_en", "creado_en"]
    list_filter = ["is_active", "bloqueado", "roles"]
    search_fields = ["email"]
    exclude = ["password", "groups", "user_permissions", "is_superuser", "last_login"]
    inlines = [UsuarioRolInline]


class DireccionInline(admin.TabularInline):
    model = Direccion
    extra = 0


class VehiculoInline(admin.TabularInline):
    model = Vehiculo
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nombres", "apellidos", "telefono", "email", "creado_en"]
    search_fields = ["nombres", "apellidos", "telefono", "numero_documento", "vehiculos__placa"]
    readonly_fields = ["acepta_datos_en", "version_politica", "anonimizado_en"]
    inlines = [DireccionInline, VehiculoInline]


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ["nombres", "apellidos", "cargo", "hace_domicilios", "activo"]


admin.site.register(Rol)


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ["creado_en", "usuario", "accion", "entidad", "entidad_id"]
    list_filter = ["accion", "entidad"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
