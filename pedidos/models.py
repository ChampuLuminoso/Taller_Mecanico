"""
Pedidos de la tienda. Por ahora: pago contra entrega o en tienda, envíos solo
en Bogotá hechos por los propios empleados.

Los precios, nombres y la dirección se COPIAN al pedido ("foto" del momento),
para que cambiar un precio o una dirección mañana no altere ventas pasadas.
"""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from cuentas.models import Cliente, Direccion, Empleado
from inventario.models import Producto


class Pedido(models.Model):
    ENVIO, RECOGER = "ENVIO", "RECOGER"
    MODALIDADES = [(ENVIO, "Envío a domicilio (Bogotá)"), (RECOGER, "Recoger en el taller")]

    CONTRA_ENTREGA, EN_TIENDA = "CONTRA_ENTREGA", "EN_TIENDA"
    METODOS_PAGO = [(CONTRA_ENTREGA, "Contra entrega"), (EN_TIENDA, "Pago en el taller")]
    # Futuro: TARJETA, CONSIGNACION, WOMPI… se agregan aquí sin cambiar el resto.

    RECIBIDO, CONFIRMADO, ALISTADO, EN_CAMINO, ENTREGADO, CANCELADO = (
        "RECIBIDO", "CONFIRMADO", "ALISTADO", "EN_CAMINO", "ENTREGADO", "CANCELADO")
    ESTADOS = [(RECIBIDO, "Recibido"), (CONFIRMADO, "Confirmado"), (ALISTADO, "Alistado"),
               (EN_CAMINO, "En camino"), (ENTREGADO, "Entregado"), (CANCELADO, "Cancelado")]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="pedidos")
    modalidad = models.CharField(max_length=8, choices=MODALIDADES)
    metodo_pago = models.CharField(max_length=16, choices=METODOS_PAGO)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=RECIBIDO)

    direccion = models.ForeignKey(Direccion, null=True, blank=True, on_delete=models.SET_NULL)
    direccion_texto = models.CharField(max_length=300, blank=True)   # la "foto"
    telefono_contacto = models.CharField(max_length=20)
    repartidor = models.ForeignKey(Empleado, null=True, blank=True, on_delete=models.PROTECT)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    costo_envio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    pagado = models.BooleanField(default=False)
    pagado_en = models.DateTimeField(null=True, blank=True)
    nota_cliente = models.CharField(max_length=500, blank=True)
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.PROTECT, related_name="+")
    confirmado_en = models.DateTimeField(null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.PROTECT, related_name="+")
    cancelado_en = models.DateTimeField(null=True, blank=True)
    motivo_cancelacion = models.CharField(max_length=200, blank=True)

    # Estados en los que el inventario YA se descontó (al confirmar).
    DESCONTADOS = [CONFIRMADO, ALISTADO, EN_CAMINO, ENTREGADO]

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.CheckConstraint(condition=Q(total=F("subtotal") + F("iva") + F("costo_envio")),
                                   name="total_cuadra"),
            models.CheckConstraint(condition=Q(modalidad="RECOGER") | ~Q(direccion_texto=""),
                                   name="envio_requiere_direccion"),
        ]

    def __str__(self):
        return f"Pedido #{self.pk} · {self.cliente} · {self.get_estado_display()}"


class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    sku = models.CharField(max_length=30)                # foto
    nombre_producto = models.CharField(max_length=150)   # foto
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)  # foto
    # Costo del producto el día de la venta: la ganancia no cambia si mañana sube el costo.
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    iva_pct = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["pedido", "producto"], name="producto_una_vez_por_pedido"),
            models.CheckConstraint(condition=Q(cantidad__gte=1), name="item_cantidad_positiva"),
        ]

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario
