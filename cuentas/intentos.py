"""
Freno contra quien intenta adivinar contraseñas:
- 5 intentos fallidos con el mismo correo → ese correo espera 15 minutos.
- 20 fallidos desde la misma IP → esa IP espera 15 minutos (más alto, porque en el
  taller varias personas comparten la misma conexión).
"""
from django.core.cache import cache

LIMITE_CORREO = 5
LIMITE_IP = 20
MINUTOS_ESPERA = 15


def _claves(email, ip):
    return {f"login:email:{(email or '').lower()}": LIMITE_CORREO, f"login:ip:{ip}": LIMITE_IP}


def esta_frenado(email, ip) -> bool:
    return any((cache.get(k) or 0) >= limite for k, limite in _claves(email, ip).items())


def registrar_fallo(email, ip):
    for k in _claves(email, ip):
        cache.add(k, 0, MINUTOS_ESPERA * 60)
        try:
            cache.incr(k)
        except ValueError:
            cache.set(k, 1, MINUTOS_ESPERA * 60)


def limpiar(email, ip):
    cache.delete(f"login:email:{(email or '').lower()}")
