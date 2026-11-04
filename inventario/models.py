"""
Inventario y apartados.

Regla de oro: las cantidades NUNCA se editan a mano. Solo cambian a través de
`inventario.servicios.mover()`, que actualiza el producto y escribe el
movimiento en la misma transacción. Así el historial siempre cuadra.
"""
from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Case, CharField, F, Q, Value, When
from django.utils import timezone

from cuentas.models import Cliente


class Categoria(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    padre = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT,
                              related_name="subcategorias")
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categorías"

    def __str__(self):
        return f"{self.padre} › {self.nombre}" if self.padre else self.nombre


class Marca(models.Model):
    nombre = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return self.nombre


class Proveedor(models.Model):
    nombre = models.CharField(max_length=100)
    nit = models.CharField(max_length=20, unique=True, null=True, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "proveedores"

    def __str__(self):
        return self.nombre


class ProductoQuerySet(models.QuerySet):
    def con_disponibilidad(self):
        """Calcula Disponible / No disponible en la consulta, sin guardarlo."""
        return self.annotate(
            unidades_disponibles=F("cantidad_fisica") - F("cantidad_apartada"),
            estado_disponibilidad=Case(
                When(Q(cantidad_fisica__gt=F("cantidad_apartada")), then=Value("Disponible")),
                default=Value("No disponible"),
                output_field=CharField(),
            ),
        )

    def bajo_stock_minimo(self):
        """Productos activos cuyo DISPONIBLE (físico − apartado) llegó al mínimo."""
        return (self.con_disponibilidad()
                .filter(activo=True, unidades_disponibles__lte=F("stock_minimo"))
                .order_by("unidades_disponibles", "nombre"))


class Producto(models.Model):
    sku = models.CharField(
        "ProductoID", max_length=30, unique=True,
        validators=[RegexValidator(r"^[A-Z0-9-]+$", "Solo mayúsculas, números y guiones.")],
    )
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    categoria = models.ForeignKey(Categoria, null=True, blank=True, on_delete=models.PROTECT)
    marca = models.ForeignKey(Marca, null=True, blank=True, on_delete=models.PROTECT)
    proveedor = models.ForeignKey(Proveedor, null=True, blank=True, on_delete=models.PROTECT)

    precio_venta = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    costo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    iva_pct = models.DecimalField("IVA %", max_digits=4, decimal_places=2, default=0)  # hoy 0; listo para cuando apliquen

    # Solo las cambia servicios.mover() — por eso editable=False.
    cantidad_fisica = models.PositiveIntegerField(default=0, editable=False)
    cantidad_apartada = models.PositiveIntegerField(default=0, editable=False)

    stock_minimo = models.PositiveIntegerField(default=0)
    imagen = models.ImageField(upload_to="productos/", blank=True)
    activo = models.BooleanField(default=True)   # "desactivar" en vez de borrar
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(auto_now=True)

    objects = ProductoQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(cantidad_apartada__lte=F("cantidad_fisica")),
                                   name="apartado_no_supera_fisico"),
        ]

    def __str__(self):
        return f"{self.sku} · {self.nombre}"

    def save(self, *args, **kwargs):
        self.sku = (self.sku or "").upper().strip()
        super().save(*args, **kwargs)

    @property
    def disponible(self) -> int:
        return self.cantidad_fisica - self.cantidad_apartada

    @property
    def disponibilidad(self) -> str:
        return "Disponible" if self.disponible > 0 else "No disponible"


class Compatibilidad(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="compatibilidades")
    marca_vehiculo = models.CharField(max_length=40)
    modelo = models.CharField(max_length=60, blank=True)   # vacío = todos los modelos de la marca
    anio_desde = models.PositiveSmallIntegerField(null=True, blank=True)
    anio_hasta = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "compatibilidades"
        constraints = [
            models.CheckConstraint(
                condition=Q(anio_desde__isnull=True) | Q(anio_hasta__isnull=True) | Q(anio_desde__lte=F("anio_hasta")),
                name="rango_anios_valido",
            ),
        ]


class MovimientoInventario(models.Model):
    ENTRADA, VENTA, AJUSTE, DEVOLUCION = "ENTRADA", "VENTA", "AJUSTE", "DEVOLUCION"
    APARTADO, LIBERACION, ENTREGA_APARTADO = "APARTADO", "LIBERACION", "ENTREGA_APARTADO"
    TIPOS = [
        (ENTRADA, "Entrada de mercancía"),
        (VENTA, "Venta"),
        (AJUSTE, "Ajuste de conteo"),
        (DEVOLUCION, "Devolución de cliente"),
        (APARTADO, "Apartado"),
        (LIBERACION, "Apartado liberado"),
        (ENTREGA_APARTADO, "Entrega de apartado"),
    ]
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    delta_fisica = models.IntegerField()      # +5 entra, −2 sale
    delta_apartada = models.IntegerField()
    saldo_fisica = models.PositiveIntegerField()
    saldo_apartada = models.PositiveIntegerField()
    motivo = models.CharField(max_length=255)
    referencia = models.CharField(max_length=60, blank=True)   # "pedido:15", "apartado:8"
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-creado_en", "-id"]
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"
        indexes = [models.Index(fields=["producto", "creado_en"])]


class SolicitudApartado(models.Model):
    """El cliente PIDE; un Subjefe o Jefe decide. Nada se descuenta hasta aprobar."""
    PENDIENTE, APROBADA, RECHAZADA, CANCELADA = "PENDIENTE", "APROBADA", "RECHAZADA", "CANCELADA"
    ESTADOS = [(PENDIENTE, "Pendiente"), (APROBADA, "Aprobada"),
               (RECHAZADA, "Rechazada"), (CANCELADA, "Cancelada por el cliente")]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="solicitudes_apartado")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    nota_cliente = models.CharField(max_length=500, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PENDIENTE)
    respuesta = models.CharField(max_length=300, blank=True)   # motivo de rechazo o indicaciones
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.PROTECT, related_name="+")
    revisada_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["creado_en"]
        verbose_name = "solicitud de apartado"
        verbose_name_plural = "solicitudes de apartado"
        constraints = [models.CheckConstraint(condition=Q(cantidad__gte=1), name="solicitud_cantidad_positiva")]


class Apartado(models.Model):
    ACTIVO, ENTREGADO, CANCELADO, VENCIDO = "ACTIVO", "ENTREGADO", "CANCELADO", "VENCIDO"
    ESTADOS = [(ACTIVO, "Activo"), (ENTREGADO, "Entregado"), (CANCELADO, "Cancelado"), (VENCIDO, "Vencido")]

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="apartados")
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="apartados")
    solicitud = models.OneToOneField(SolicitudApartado, null=True, blank=True,
                                     on_delete=models.PROTECT, related_name="apartado")
    cantidad = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    abono = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ACTIVO)
    vence_en = models.DateTimeField()
    nota = models.CharField(max_length=300, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(default=timezone.now)
    cerrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["vence_en"]
        indexes = [models.Index(fields=["estado", "vence_en"])]
        constraints = [models.CheckConstraint(condition=Q(cantidad__gte=1), name="apartado_cantidad_positiva")]

    def __str__(self):
        return f"Apartado #{self.pk} · {self.producto.sku} × {self.cantidad}"
