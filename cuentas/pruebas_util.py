"""Ayudantes para las pruebas: crear usuarios con rol en una línea."""
from datetime import date

from django.utils import timezone

from .models import Cliente, Rol, Usuario, UsuarioRol


def usuario_con_rol(email, *codigos, password="ClaveSegura-2026"):
    u = Usuario.todos.create_user(email=email, password=password)
    for codigo in codigos:
        UsuarioRol.objects.create(usuario=u, rol=Rol.objects.get(codigo=codigo))
    return u


def cliente_con_cuenta(email="cliente@correo.co", nombres="Ana", apellidos="Rojas"):
    u = usuario_con_rol(email, "CLIENTE")
    c = Cliente.objects.create(
        usuario=u, nombres=nombres, apellidos=apellidos, telefono="3001234567", email=email,
        fecha_nacimiento=date(1995, 5, 20), acepta_datos_en=timezone.now(), version_politica="v1",
    )
    return u, c
