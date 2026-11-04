from django.db import migrations

CATEGORIAS = ["Frenos", "Suspensión", "Motor", "Eléctricos", "Filtros", "Aceites"]


def crear(apps, schema_editor):
    Categoria = apps.get_model("inventario", "Categoria")
    for nombre in CATEGORIAS:
        Categoria.objects.get_or_create(nombre=nombre)


class Migration(migrations.Migration):
    dependencies = [("inventario", "0002_movimientos_inmutables")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
