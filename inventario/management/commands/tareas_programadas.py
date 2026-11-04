"""python manage.py tareas_programadas

Una sola tarea que Railway corre cada hora (servicio "cron"):
  1. Libera los apartados vencidos (siempre: si no hay ninguno, no hace nada).
  2. Desde las 5:00 p. m. (hora de Bogotá) envía el recordatorio de las citas de mañana.
     Cada cita se recuerda una sola vez, aunque la tarea corra varias veces esa tarde.
Al terminar, el proceso sale: así Railway sabe que la tarea acabó y apaga el contenedor."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from citas.servicios import enviar_recordatorios
from cuentas.models import Usuario
from inventario.servicios import vencer_apartados

HORA_RECORDATORIOS = 17


class Command(BaseCommand):
    help = "Tareas automáticas: vencer apartados y recordar citas de mañana."

    def handle(self, *args, **opts):
        ahora = timezone.localtime()
        vencidos = vencer_apartados(Usuario.sistema())
        recordados = enviar_recordatorios() if ahora.hour >= HORA_RECORDATORIOS else 0
        self.stdout.write(f"{ahora:%Y-%m-%d %H:%M} · apartados vencidos: {vencidos} · recordatorios: {recordados}")
