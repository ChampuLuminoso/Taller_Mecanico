"""Usuario técnico para tareas automáticas (vencer apartados de noche).
No puede iniciar sesión: no tiene contraseña utilizable ni roles."""
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def crear(apps, schema_editor):
    Usuario = apps.get_model("cuentas", "Usuario")
    Usuario.objects.get_or_create(
        email=settings.TALLER["EMAIL_SISTEMA"],
        defaults={"password": make_password(None), "is_active": False},
    )


class Migration(migrations.Migration):
    dependencies = [("cuentas", "0002_roles_y_auditoria_inmutable")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
