# Imagen del sitio para Railway (o cualquier servidor con Docker).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Primero solo las dependencias: si no cambian, Docker reutiliza esta capa y publicar es más rápido.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Archivos estáticos (CSS, JS, fuentes, logo) con huella en el nombre. No necesita la base de datos.
RUN DJANGO_SECRET_KEY=solo-para-construir python manage.py collectstatic --noinput

# Usuario sin privilegios: si alguien encontrara una falla, no tendría control total del contenedor.
# (iniciar.sh arranca como root solo para preparar el volumen de fotos y enseguida cambia a este usuario.)
RUN useradd --create-home --uid 1000 taller && chown -R taller /app

EXPOSE 8000
CMD ["sh", "iniciar.sh"]
