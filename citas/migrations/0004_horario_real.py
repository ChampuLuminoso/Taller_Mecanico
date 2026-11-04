"""Horario confirmado por los dueños: L–V 8:00–18:00, sábado 9:00–16:00, domingo cerrado."""
from datetime import time

from django.db import migrations

HORARIO = {d: (time(8), time(18)) for d in range(5)}
HORARIO[5] = (time(9), time(16))


def aplicar(apps, schema_editor):
    HorarioTaller = apps.get_model("citas", "HorarioTaller")
    for dia in range(7):
        abre, cierra = HORARIO.get(dia, (None, None))
        HorarioTaller.objects.update_or_create(
            dia_semana=dia, defaults={"abierto": dia in HORARIO, "abre": abre, "cierra": cierra})


class Migration(migrations.Migration):
    dependencies = [("citas", "0003_datos_iniciales")]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
