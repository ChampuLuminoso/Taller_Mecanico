"""Crea los roles base y vuelve la auditoría inmutable a nivel de PostgreSQL."""
from django.db import migrations

ROLES = [
    ("CLIENTE", "Cliente"),
    ("EMPLEADO", "Empleado"),
    ("SUBJEFE", "Subjefe"),
    ("JEFE", "Jefe"),
    ("INGENIERO", "Ingeniero / soporte técnico"),
]

FUNCION = """
CREATE OR REPLACE FUNCTION impedir_cambios_auditoria() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'La tabla % solo admite inserciones', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
"""


def trigger(tabla):
    return (
        f"CREATE TRIGGER {tabla}_solo_insertar BEFORE UPDATE OR DELETE ON {tabla} "
        f"FOR EACH ROW EXECUTE FUNCTION impedir_cambios_auditoria();",
        f"DROP TRIGGER IF EXISTS {tabla}_solo_insertar ON {tabla};",
    )


def crear_roles(apps, schema_editor):
    Rol = apps.get_model("cuentas", "Rol")
    for codigo, nombre in ROLES:
        Rol.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre})


class Migration(migrations.Migration):
    dependencies = [("cuentas", "0001_initial")]

    operations = [
        migrations.RunPython(crear_roles, migrations.RunPython.noop),
        migrations.RunSQL(FUNCION, "DROP FUNCTION IF EXISTS impedir_cambios_auditoria();"),
        migrations.RunSQL(*trigger("cuentas_auditoria")),
        migrations.RunSQL(*trigger("cuentas_auditoriafran")),
    ]
