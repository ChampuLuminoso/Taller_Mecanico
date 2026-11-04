"""Validadores reutilizables de datos de personas y vehículos."""
import re
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


def calcular_edad(fecha_nacimiento: date, hoy: date | None = None) -> int:
    """Edad en años cumplidos (en hora de Bogotá, no del servidor)."""
    hoy = hoy or timezone.localdate()
    cumplio_este_anio = (hoy.month, hoy.day) >= (fecha_nacimiento.month, fecha_nacimiento.day)
    return hoy.year - fecha_nacimiento.year - (0 if cumplio_este_anio else 1)


def validar_mayor_de_edad(fecha_nacimiento: date) -> None:
    """Solo personas mayores de edad pueden tener cuenta o comprar."""
    hoy = timezone.localdate()
    if fecha_nacimiento > hoy:
        raise ValidationError("La fecha de nacimiento no puede estar en el futuro.")
    edad = calcular_edad(fecha_nacimiento, hoy)
    if edad > 120:
        raise ValidationError("Revisa la fecha de nacimiento.")
    minima = settings.TALLER["EDAD_MINIMA"]
    if edad < minima:
        raise ValidationError(f"Debes tener al menos {minima} años para registrarte.")


# Carros: ABC123 · Motos: ABC12D
PLACA_RE = re.compile(r"^[A-Z]{3}\d{3}$|^[A-Z]{3}\d{2}[A-Z]$")


def validar_placa(valor: str) -> None:
    if not PLACA_RE.match(valor or ""):
        raise ValidationError("Placa inválida. Formato: ABC123 (carro) o ABC12D (moto).")


def validar_telefono_co(valor: str) -> None:
    digitos = re.sub(r"\D", "", valor or "")
    if digitos.startswith("57"):
        digitos = digitos[2:]
    if len(digitos) != 10:
        raise ValidationError("Escribe un número de 10 dígitos, por ejemplo 3001234567.")
