"""Almuerzo confirmado por los dueños: de 1:00 a 2:00 p. m. todos los días que abren."""
from datetime import time

from django.db import migrations


def aplicar(apps, schema_editor):
    HorarioTaller = apps.get_model("citas", "HorarioTaller")
    HorarioTaller.objects.filter(abierto=True).update(almuerzo_inicio=time(13), almuerzo_fin=time(14))


class Migration(migrations.Migration):
    dependencies = [("citas", "0005_agenda_fase4")]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
