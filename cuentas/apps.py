from django.apps import AppConfig


class CuentasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cuentas"

    def ready(self):
        from . import senales  # noqa: F401  (conecta las señales de inicio de sesión)
