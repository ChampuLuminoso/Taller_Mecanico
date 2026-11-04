"""python manage.py crear_fran --email correo@fran.co

Crea la cuenta única de Fran. Si ya existe, la base de datos lo impide.
Lo ejecuta el Ingeniero, idealmente con Fran al lado escribiendo su propia contraseña."""
from getpass import getpass

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from cuentas.auditoria import crear_fran, registrar
from cuentas.models import Usuario


class Command(BaseCommand):
    help = "Crea la cuenta única de Fran."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, email, **opts):
        email = email.strip().lower()
        if Usuario.todos.filter(es_fran=True).exists():
            raise CommandError("Ya existe la cuenta de Fran. Solo puede haber una.")
        if Usuario.todos.filter(email__iexact=email).exists():
            raise CommandError("Ya existe una cuenta con ese correo.")
        clave = getpass("Contraseña de Fran: ")
        if clave != getpass("Repite la contraseña: "):
            raise CommandError("Las contraseñas no coinciden.")
        try:
            password_validation.validate_password(clave)
        except ValidationError as e:
            raise CommandError(" ".join(e.messages))
        try:
            with transaction.atomic():
                u = crear_fran(email, clave)
                registrar(u, "crear_fran", "Usuario", u.pk, despues={"origen": "consola"})  # va a su auditoría
        except IntegrityError:
            raise CommandError("Ya existe la cuenta de Fran. Solo puede haber una.")
        # Mensaje discreto: no deja rastro del rol en la terminal.
        self.stdout.write(self.style.SUCCESS("Cuenta creada."))
