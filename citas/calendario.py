"""
Calendario laboral colombiano del taller.

Orden de decisión para un día:
  1. Excepción del taller (CERRADO / ABIERTO) → manda sobre todo lo demás.
  2. Festivo nacional (librería `holidays`, ya aplica la Ley Emiliani).
  3. Horario semanal del taller (domingo cerrado, sábado medio día...).

⚠ Los festivos cambian por ley (en 2026 se creó el de la Virgen de Chiquinquirá).
   Actualiza la librería `holidays` cada año y, si una ley o la Corte cambia algo
   antes de que la librería se actualice, corrígelo con una ExcepcionCalendario.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache

import holidays
from django.utils import timezone

LABORAL, NO_LABORAL = "LABORAL", "NO_LABORAL"


@dataclass
class InfoDia:
    fecha: date
    tipo: str            # LABORAL / NO_LABORAL
    motivo: str          # "Festivo: Navidad", "Domingo", "Cerrado: inventario anual"...
    abre: time | None = None
    cierra: time | None = None
    almuerzo_inicio: time | None = None
    almuerzo_fin: time | None = None


@lru_cache(maxsize=16)
def _festivos(anio: int):
    return holidays.CO(years=anio, language="es")


def nombre_festivo(fecha: date) -> str | None:
    return _festivos(fecha.year).get(fecha)


def info_dia(fecha: date) -> InfoDia:
    from .models import ExcepcionCalendario, HorarioTaller

    horario = HorarioTaller.objects.filter(dia_semana=fecha.weekday()).first()
    excepcion = ExcepcionCalendario.objects.filter(fecha=fecha).first()

    if excepcion and excepcion.tipo == ExcepcionCalendario.CERRADO:
        return InfoDia(fecha, NO_LABORAL, f"Cerrado: {excepcion.motivo}")

    if excepcion and excepcion.tipo == ExcepcionCalendario.ABIERTO:
        # Abre excepcionalmente; usa el horario de lunes a viernes como referencia.
        base = HorarioTaller.objects.filter(dia_semana=0).first()
        return InfoDia(fecha, LABORAL, f"Abierto: {excepcion.motivo}", base.abre, base.cierra,
                       base.almuerzo_inicio, base.almuerzo_fin)

    festivo = nombre_festivo(fecha)
    if festivo:
        return InfoDia(fecha, NO_LABORAL, f"Festivo: {festivo}")

    if not horario or not horario.abierto:
        return InfoDia(fecha, NO_LABORAL, "Cerrado" if fecha.weekday() != 6 else "Domingo")

    return InfoDia(fecha, LABORAL, "", horario.abre, horario.cierra,
                   horario.almuerzo_inicio, horario.almuerzo_fin)


def es_laboral(fecha: date) -> bool:
    return info_dia(fecha).tipo == LABORAL


def sumar_dias_habiles(desde: datetime, dias: int) -> datetime:
    """Fecha-hora `dias` días hábiles después (se usa para vencer apartados).
    Vence al cierre del taller de ese día."""
    actual = timezone.localtime(desde).date()
    contados = 0
    while contados < dias:
        actual += timedelta(days=1)
        if es_laboral(actual):
            contados += 1
    info = info_dia(actual)
    return timezone.make_aware(datetime.combine(actual, info.cierra or time(18, 0)))


def mes(anio: int, mes_: int) -> list[InfoDia]:
    """Todos los días del mes con su estado, para pintar el calendario."""
    dia = date(anio, mes_, 1)
    dias = []
    while dia.month == mes_:
        dias.append(info_dia(dia))
        dia += timedelta(days=1)
    return dias
