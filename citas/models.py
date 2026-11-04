"""
Agenda de citas.

Capacidad = 3 bahías (puestos de trabajo). Cada cita ocupa una bahía en un rango
de tiempo, y PostgreSQL impide que dos citas activas se crucen en la misma bahía.
"""
from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Func, Q
from django.utils import timezone

from cuentas.models import Cliente, Vehiculo


class TsTzRange(Func):
    """tstzrange(inicio, fin, '[)') de PostgreSQL: rango de fecha-hora con zona horaria."""
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class TipoVisita(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    duracion_min = models.PositiveIntegerField(validators=[MinValueValidator(15)])
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "tipo de visita"
        verbose_name_plural = "tipos de visita"

    def __str__(self):
        return f"{self.nombre} ({self.duracion_min} min)"


class Bahia(models.Model):
    nombre = models.CharField(max_length=30, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "bahía"

    def __str__(self):
        return self.nombre


class HorarioTaller(models.Model):
    DIAS = [(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"),
            (4, "Viernes"), (5, "Sábado"), (6, "Domingo")]
    dia_semana = models.PositiveSmallIntegerField(choices=DIAS, unique=True)
    abierto = models.BooleanField(default=True)
    abre = models.TimeField(null=True, blank=True)
    cierra = models.TimeField(null=True, blank=True)
    # En el almuerzo no se reciben vehículos: ninguna cita puede cruzar esa franja.
    almuerzo_inicio = models.TimeField(null=True, blank=True)
    almuerzo_fin = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["dia_semana"]
        verbose_name = "horario"
        verbose_name_plural = "horario del taller"
        constraints = [
            models.CheckConstraint(
                condition=Q(abierto=False) | Q(abre__isnull=False, cierra__isnull=False, abre__lt=F("cierra")),
                name="horario_coherente",
            ),
            models.CheckConstraint(
                condition=Q(almuerzo_inicio__isnull=True, almuerzo_fin__isnull=True)
                | Q(almuerzo_inicio__isnull=False, almuerzo_fin__isnull=False, almuerzo_inicio__lt=F("almuerzo_fin")),
                name="almuerzo_coherente",
            ),
        ]

    def __str__(self):
        return f"{self.get_dia_semana_display()}: {self.abre}–{self.cierra}" if self.abierto else f"{self.get_dia_semana_display()}: cerrado"


class ExcepcionCalendario(models.Model):
    """Días que el taller define a mano, por encima de festivos y horario:
    CERRADO (vacaciones, inventario) o ABIERTO (abrir un festivo excepcionalmente)."""
    CERRADO, ABIERTO = "CERRADO", "ABIERTO"
    fecha = models.DateField(unique=True)
    tipo = models.CharField(max_length=8, choices=[(CERRADO, "Cerrado"), (ABIERTO, "Abierto")])
    motivo = models.CharField(max_length=150)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["fecha"]
        verbose_name = "excepción de calendario"
        verbose_name_plural = "excepciones de calendario"

    def __str__(self):
        return f"{self.fecha} · {self.get_tipo_display()} · {self.motivo}"


class BloqueoAgenda(models.Model):
    """Bloquear horas concretas (p. ej. martes 2–4 p. m.). Sin bahía = todo el taller."""
    inicio = models.DateTimeField()
    fin = models.DateTimeField()
    bahia = models.ForeignKey(Bahia, null=True, blank=True, on_delete=models.CASCADE)
    motivo = models.CharField(max_length=150)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "bloqueo de agenda"
        verbose_name_plural = "bloqueos de agenda"
        constraints = [models.CheckConstraint(condition=Q(fin__gt=F("inicio")), name="bloqueo_fin_despues_inicio")]


class Cita(models.Model):
    PENDIENTE, CONFIRMADA, CANCELADA, ATENDIDA, NO_ASISTIO = (
        "PENDIENTE", "CONFIRMADA", "CANCELADA", "ATENDIDA", "NO_ASISTIO")
    ESTADOS = [(PENDIENTE, "Pendiente"), (CONFIRMADA, "Confirmada"), (CANCELADA, "Cancelada"),
               (ATENDIDA, "Atendida"), (NO_ASISTIO, "No asistió")]
    ACTIVAS = [PENDIENTE, CONFIRMADA]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="citas")
    vehiculo = models.ForeignKey(Vehiculo, null=True, blank=True, on_delete=models.PROTECT)
    tipo_visita = models.ForeignKey(TipoVisita, on_delete=models.PROTECT)
    bahia = models.ForeignKey(Bahia, on_delete=models.PROTECT)
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField()
    nota_cliente = models.CharField("síntomas del vehículo", max_length=800, blank=True)
    # Si el sistema la aceptó es porque había cupo: queda confirmada de una vez.
    estado = models.CharField(max_length=10, choices=ESTADOS, default=CONFIRMADA)
    motivo_cancelacion = models.CharField(max_length=200, blank=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="+")
    cancelada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.PROTECT, related_name="+")
    cancelada_en = models.DateTimeField(null=True, blank=True)
    veces_reprogramada = models.PositiveSmallIntegerField(default=0)
    recordatorio_enviado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["inicio"]
        constraints = [
            models.CheckConstraint(condition=Q(fin__gt=F("inicio")), name="cita_fin_despues_inicio"),
            # La regla anti doble reserva vive en la base de datos:
            # dos citas ACTIVAS no pueden solaparse en la misma bahía.
            ExclusionConstraint(
                name="cita_sin_cruce_por_bahia",
                expressions=[
                    (TsTzRange("inicio", "fin", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("bahia", RangeOperators.EQUAL),
                ],
                condition=Q(estado__in=["PENDIENTE", "CONFIRMADA"]),
            ),
        ]

    def __str__(self):
        local = timezone.localtime(self.inicio)
        return f"{local:%d/%m/%Y %H:%M} · {self.tipo_visita.nombre} · {self.cliente}"
