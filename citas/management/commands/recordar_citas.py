"""python manage.py recordar_citas

Envía por correo el recordatorio de las citas de mañana.
En producción se programa cada tarde (por ejemplo, a las 5:00 p. m.)."""
from django.core.management.base import BaseCommand

from citas.servicios import enviar_recordatorios


class Command(BaseCommand):
    help = "Envía el recordatorio de las citas de mañana."

    def handle(self, *args, **opts):
        self.stdout.write(self.style.SUCCESS(f"Recordatorios enviados: {enviar_recordatorios()}"))
