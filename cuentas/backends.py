from django.contrib.auth.backends import ModelBackend

from .models import Usuario


class BackendTaller(ModelBackend):
    """Igual al login normal de Django, con dos diferencias:
    1. Busca en `Usuario.todos`, para que Fran (oculto en todo lo demás) pueda entrar.
    2. Rechaza cuentas bloqueadas o eliminadas aunque la contraseña sea correcta."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get("email")
        if not email or password is None:
            return None
        try:
            usuario = Usuario.todos.get_by_natural_key(email)
        except Usuario.DoesNotExist:
            Usuario().set_password(password)  # mismo tiempo de respuesta: no revela si el correo existe
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None

    def user_can_authenticate(self, user):
        return user.puede_entrar

    def get_user(self, user_id):
        try:
            usuario = Usuario.todos.get(pk=user_id)
        except Usuario.DoesNotExist:
            return None
        return usuario if self.user_can_authenticate(usuario) else None
