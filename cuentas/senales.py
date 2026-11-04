"""Cada inicio de sesión (exitoso o fallido) queda en la auditoría."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .auditoria import registrar
from .decoradores import ip_de
from .models import AuditoriaFran, Usuario


@receiver(user_logged_in)
def al_entrar(sender, request, user, **kwargs):
    registrar(user, "inicio_sesion", "Usuario", user.pk, ip=ip_de(request) if request else None)


@receiver(user_logged_out)
def al_salir(sender, request, user, **kwargs):
    if user:
        registrar(user, "cierre_sesion", "Usuario", user.pk, ip=ip_de(request) if request else None)


@receiver(user_login_failed)
def al_fallar(sender, credentials, request=None, **kwargs):
    email = (credentials.get("username") or "").lower()
    ip = ip_de(request) if request else None
    if Usuario.todos.filter(email__iexact=email, es_fran=True).exists():
        # Un intento contra la cuenta de Fran solo lo ve Fran.
        AuditoriaFran.objects.create(accion="inicio_sesion_fallido", entidad="Usuario",
                                     despues={"email": email}, ip=ip)
    else:
        registrar(None, "inicio_sesion_fallido", "Usuario", despues={"email": email}, ip=ip)
