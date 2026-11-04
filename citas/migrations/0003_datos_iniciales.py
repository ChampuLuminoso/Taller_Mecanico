"""Datos iniciales del taller. Todo se puede cambiar luego desde el admin."""
from datetime import time

from django.db import migrations

TIPOS = [
    ("Revisión general", 90),
    ("Cambio de aceite", 45),
    ("Frenos", 120),
    ("Diagnóstico", 60),
    ("Suspensión", 120),
    ("Sincronización", 90),
]

# Supuesto inicial (confírmalo con los dueños): L–V 8:00–17:00, sábado 8:00–13:00, domingo cerrado.
HORARIO = {0: (time(8), time(17)), 1: (time(8), time(17)), 2: (time(8), time(17)),
           3: (time(8), time(17)), 4: (time(8), time(17)), 5: (time(8), time(13))}


def sembrar(apps, schema_editor):
    Bahia = apps.get_model("citas", "Bahia")
    TipoVisita = apps.get_model("citas", "TipoVisita")
    HorarioTaller = apps.get_model("citas", "HorarioTaller")

    for n in (1, 2, 3):   # capacidad actual: 3 vehículos a la vez
        Bahia.objects.get_or_create(nombre=f"Bahía {n}")
    for orden, (nombre, minutos) in enumerate(TIPOS):
        TipoVisita.objects.get_or_create(nombre=nombre, defaults={"duracion_min": minutos, "orden": orden})
    for dia in range(7):
        abre, cierra = HORARIO.get(dia, (None, None))
        HorarioTaller.objects.get_or_create(
            dia_semana=dia, defaults={"abierto": dia in HORARIO, "abre": abre, "cierra": cierra})


class Migration(migrations.Migration):
    dependencies = [("citas", "0002_initial")]
    operations = [migrations.RunPython(sembrar, migrations.RunPython.noop)]
