from django.contrib import admin

from .models import Pedido, PedidoItem


class ItemInline(admin.TabularInline):
    model = PedidoItem
    extra = 0


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ["pk", "creado_en", "cliente", "modalidad", "metodo_pago", "estado", "total", "pagado"]
    list_filter = ["estado", "modalidad", "metodo_pago", "pagado"]
    inlines = [ItemInline]
