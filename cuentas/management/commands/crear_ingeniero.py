"""python manage.py crear_ingeniero --email jorge@correo.co

Crea la cuenta del Ingeniero (soporte técnico). Pide la contraseña sin mostrarla en pantalla.
Solo existe por consola: nadie puede crear ingenieros desde la web."""
from getpass import getpass

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cuentas.auditoria import registrar
from cuentas.models import Rol, Usuario, UsuarioRol


class Command(BaseCommand):
    help = "Crea la cuenta del Ingeniero (soporte técnico de la plataforma)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, email, **opts):
        email = email.strip().lower()
        if Usuario.todos.filter(email__iexact=email).exists():
            raise CommandError("Ya existe una cuenta con ese correo.")
        clave = getpass("Contraseña: ")
        if clave != getpass("Repite la contraseña: "):
            raise CommandError("Las contraseñas no coinciden.")
        try:
            password_validation.validate_password(clave)
        except ValidationError as e:
            raise CommandError(" ".join(e.messages))

        with transaction.atomic():
            # is_staff + is_superuser: entra al admin como "puerta de emergencia" técnica.
            u = Usuario.todos.create_superuser(email=email, password=clave)
            UsuarioRol.objects.create(usuario=u, rol=Rol.objects.get(codigo=Rol.INGENIERO))
            registrar(u, "crear_ingeniero", "Usuario", u.pk, despues={"origen": "consola"})
        self.stdout.write(self.style.SUCCESS(f"Ingeniero creado: {email}"))
