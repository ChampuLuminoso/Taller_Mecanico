from django.contrib import admin

from .models import (Apartado, Categoria, Compatibilidad, Marca, MovimientoInventario, Producto,
                     Proveedor, SolicitudApartado)


class CompatibilidadInline(admin.TabularInline):
    model = Compatibilidad
    extra = 0


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["sku", "nombre", "precio_venta", "cantidad_fisica", "cantidad_apartada",
                    "disponibilidad", "activo"]
    list_editable = ["precio_venta", "activo"]     # edición rápida desde la tabla
    list_filter = ["activo", "categoria", "marca"]
    search_fields = ["sku", "nombre", "compatibilidades__marca_vehiculo", "compatibilidades__modelo"]
    readonly_fields = ["cantidad_fisica", "cantidad_apartada", "creado_en", "actualizado_en"]
    inlines = [CompatibilidadInline]


@admin.register(MovimientoInventario)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ["creado_en", "producto", "tipo", "delta_fisica", "delta_apartada",
                    "saldo_fisica", "usuario", "motivo"]
    list_filter = ["tipo"]

    def has_add_permission(self, request):
        return False   # solo por servicios.mover()

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SolicitudApartado)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = ["creado_en", "cliente", "producto", "cantidad", "estado"]
    list_filter = ["estado"]


@admin.register(Apartado)
class ApartadoAdmin(admin.ModelAdmin):
    list_display = ["pk", "producto", "cliente", "cantidad", "abono", "estado", "vence_en"]
    list_filter = ["estado"]
    readonly_fields = ["estado", "cantidad", "producto", "creado_por", "cerrado_en"]


admin.site.register([Categoria, Marca, Proveedor])
