"""python manage.py vencer_apartados

Libera los apartados que pasaron su fecha de vencimiento.
En producción se programa para correr cada noche (por ejemplo, a las 11:55 p. m.)."""
from django.core.management.base import BaseCommand

from cuentas.models import Usuario
from inventario.servicios import vencer_apartados


class Command(BaseCommand):
    help = "Marca como VENCIDOS los apartados expirados y devuelve las unidades al stock."

    def handle(self, *args, **opts):
        n = vencer_apartados(Usuario.sistema())
        self.stdout.write(self.style.SUCCESS(f"Apartados vencidos: {n}"))
