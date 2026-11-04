"""El historial de inventario tampoco se edita ni se borra: un error se corrige con un AJUSTE."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0001_initial"),
        ("cuentas", "0002_roles_y_auditoria_inmutable"),  # ahí se crea la función
    ]

    operations = [
        migrations.RunSQL(
            "CREATE TRIGGER inventario_movimiento_solo_insertar BEFORE UPDATE OR DELETE "
            "ON inventario_movimientoinventario FOR EACH ROW EXECUTE FUNCTION impedir_cambios_auditoria();",
            "DROP TRIGGER IF EXISTS inventario_movimiento_solo_insertar ON inventario_movimientoinventario;",
        ),
    ]
