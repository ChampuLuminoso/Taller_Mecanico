"""
Configuración de AutoPartes M&F · Taller Mecánico Francois.

Los secretos (clave, contraseña de la base de datos, llave del correo) se leen de variables
de entorno: nunca se escriben en el código ni se suben a Git.

SEGURO POR DEFECTO: si no se dice nada, el sitio arranca en modo producción (DEBUG apagado,
HTTPS obligatorio). En tu computador, el archivo .env enciende el modo desarrollo.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .entorno import booleano, cargar, lista

BASE_DIR = Path(__file__).resolve().parent.parent
cargar(BASE_DIR / ".env")

DEBUG = booleano("DJANGO_DEBUG")
# Las pruebas automáticas corren sin HTTPS ni secretos reales.
PRUEBAS = booleano("PRUEBAS") or (len(__import__("sys").argv) > 1 and __import__("sys").argv[1] == "test")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not (DEBUG or PRUEBAS):
        raise ImproperlyConfigured("Falta DJANGO_SECRET_KEY. En Railway agrégala en Variables.")
    SECRET_KEY = "solo-para-desarrollo-nunca-en-produccion"

# Dominios permitidos. Railway pone su dominio en RAILWAY_PUBLIC_DOMAIN; el propio se agrega en DJANGO_ALLOWED_HOSTS.
ALLOWED_HOSTS = lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
if os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
    ALLOWED_HOSTS.append(os.environ["RAILWAY_PUBLIC_DOMAIN"])
ALLOWED_HOSTS.append("healthcheck.railway.app")   # desde aquí Railway revisa que el sitio esté vivo
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

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
    "anymail",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",      # sirve CSS, JS, fuentes y logo, comprimidos y con caché larga
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
                "cuentas.navegacion.contexto",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL desde el día 1 (las reglas de citas usan funciones propias de Postgres).
# En Railway llega todo en DATABASE_URL; en tu computador, por las variables DB_* del .env.
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=60, conn_health_checks=True)}
else:
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

# Caché en la base de datos: así el freno de intentos de login se comparte entre todos los procesos
# del servidor (con la caché en memoria, cada proceso llevaría su propia cuenta y el freno se debilita).
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "cache_taller"}}

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
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # En producción cada archivo lleva una huella en el nombre (marca.3f9a1c.css): el navegador lo guarda
    # por un año y, cuando cambia, el nombre cambia solo. En pruebas se usa el almacenamiento simple.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
                    if not (DEBUG or PRUEBAS) else "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_URL = "media/"
# Fotos de productos. En Railway van en un volumen (disco que no se borra al publicar una versión nueva).
MEDIA_ROOT = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.environ.get("MEDIA_ROOT") or BASE_DIR / "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Sesiones e inicio de sesión ──
LOGIN_URL = "cuentas:login"
LOGIN_REDIRECT_URL = "cuentas:panel"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14      # "recordarme": 14 días
SESSION_COOKIE_HTTPONLY = True              # JavaScript no puede leer la cookie de sesión
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# ── HTTPS y cabeceras de seguridad (solo en producción) ──
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not (DEBUG or PRUEBAS)
SECURE_REDIRECT_EXEMPT = [r"^salud/$"]                       # la revisión de Railway entra por http interno
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # Railway atiende el HTTPS y nos pasa la petición
# HSTS: el navegador recuerda "este sitio es solo HTTPS". Se empieza con 1 hora; cuando el dominio
# propio funcione bien, súbelo a 31536000 (un año) con la variable DJANGO_HSTS_SEGUNDOS.
SECURE_HSTS_SECONDS = 0 if DEBUG else int(os.environ.get("DJANGO_HSTS_SEGUNDOS", "3600"))
# Cuando el dominio lleve una semana funcionando bien: DJANGO_HSTS_SEGUNDOS=31536000 y DJANGO_HSTS_COMPLETO=1.
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_PRELOAD = booleano("DJANGO_HSTS_COMPLETO")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Cuántos proxies hay delante (Railway = 1). Sirve para saber la IP real del cliente en la auditoría.
PROXIES_DE_CONFIANZA = int(os.environ.get("PROXIES_DE_CONFIANZA", "0" if DEBUG else "1"))

# ── Correo ──
# Desarrollo: los correos se imprimen en la terminal.
# Railway (plan Hobby bloquea SMTP): se envían por la API de Resend, con la llave en RESEND_API_KEY.
# Remitente: avisos@<tu dominio> (dominio verificado en Resend). Las respuestas llegan a CORREO_RESPUESTA.
if os.environ.get("RESEND_API_KEY"):
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
    ANYMAIL = {"RESEND_API_KEY": os.environ["RESEND_API_KEY"]}
else:
    EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "AutoPartes M&F <avisos@autopartes.local>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
CORREO_RESPUESTA = os.environ.get("CORREO_RESPUESTA", "")

# ── Registros (logs): en producción salen por la consola y Railway los muestra en "Logs" ──
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {asctime} {name}: {message}", "style": "{"}},
    "handlers": {"consola": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["consola"], "level": "INFO" if not DEBUG else "WARNING"},
    "loggers": {"django.request": {"handlers": ["consola"], "level": "ERROR", "propagate": False}},
}

# Imágenes de productos
TAMANO_MAX_IMAGEN_MB = 3

# ── Reglas del negocio (se pueden ajustar sin tocar el código de las apps) ──
MARCA = {
    "NOMBRE": os.environ.get("MARCA_NOMBRE", "AutoPartes M&F"),          # el nombre que trae el logo
    "SUBTITULO": os.environ.get("MARCA_SUBTITULO", "Taller Mecánico Francois"),
    "DESDE": 2012,
    "CIUDAD": "Bogotá",
}

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
