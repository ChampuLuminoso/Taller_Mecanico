"""
Configuración de Taller Mecánico Francois.

Los secretos (clave, contraseña de la base de datos) se leen de variables de
entorno: nunca se escriben en el código ni se suben a Git.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "solo-para-desarrollo-cambiar-en-produccion")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Apps del taller
    "cuentas",
    "inventario",
    "pedidos",
    "citas",
    "reportes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pedidos.contexto.tienda",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL desde el día 1 (las reglas de citas usan funciones propias de Postgres).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "taller_francois"),
        "USER": os.environ.get("DB_USER", "taller"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "taller"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Usuario propio: se define ANTES de la primera migración (cambiarlo después es muy doloroso).
AUTH_USER_MODEL = "cuentas.Usuario"

# Este backend sabe encontrar también al usuario oculto (Fran) para que pueda iniciar sesión.
AUTHENTICATION_BACKENDS = ["cuentas.backends.BackendTaller"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Sesiones e inicio de sesión ──
LOGIN_URL = "cuentas:login"
LOGIN_REDIRECT_URL = "cuentas:panel"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14      # "recordarme": 14 días
SESSION_COOKIE_HTTPONLY = True              # JavaScript no puede leer la cookie de sesión
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# En producción (HTTPS) estas tres van en True; con DEBUG local deben ir en False.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG

# ── Correo ──
# En desarrollo los correos se imprimen en la terminal. En producción se configura SMTP
# con variables de entorno (por ejemplo, el correo del taller en Gmail/Outlook o un servicio de envío).
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "notificaciones@tallerfrancois.local")

# Imágenes de productos
TAMANO_MAX_IMAGEN_MB = 3

# ── Reglas del negocio (se pueden ajustar sin tocar el código de las apps) ──
TALLER = {
    "URL_SITIO": os.environ.get("URL_SITIO", "http://localhost:8000"),   # para enlaces en correos
    "EMAIL_SISTEMA": "sistema@tallerfrancois.local",   # usuario técnico de tareas automáticas
    "EDAD_MINIMA": 18,
    "VERSION_POLITICA": "2026-11-v1",   # súbela cada vez que cambie el texto de la política
    "CIUDAD_ENVIOS": "Bogotá D.C.",
    "WHATSAPP_JEFE": os.environ.get("WHATSAPP_JEFE", ""),  # ej. 573001234567
    "DIAS_VENCE_APARTADO": 3,          # días hábiles sin abono
    "DIAS_VENCE_APARTADO_ABONO": 7,    # días hábiles con abono
    "INTERVALO_CITAS_MIN": 30,         # cada cuánto empieza una franja
    "COSTO_ENVIO": 2000,               # domicilio en Bogotá, tarifa fija por ahora
    "MAX_UNIDADES_POR_PRODUCTO": 20,   # tope por línea del carrito
    "TEXTO_ENTREGAS": "Las entregas se hacen principalmente los sábados. Te llamaremos para acordar la hora.",
    "CITAS_ANTICIPACION_MIN_HORAS": 3, # el cliente agenda mínimo 3 horas antes
    "CITAS_MAX_DIAS": 20,              # y máximo 20 días hacia adelante
    "CITAS_LIMITE_CAMBIO_HORAS": 4,    # cancelar o cambiar: hasta 4 horas antes
    "CITAS_MAX_ACTIVAS_CLIENTE": 3,    # citas futuras a la vez por cliente (evita acaparar cupos)
}
