#!/bin/sh
# Arranque en Railway.
#   sh iniciar.sh          → servicio web: aplica cambios de la base de datos y enciende el servidor
#   sh iniciar.sh tareas   → servicio cron: tareas de cada hora (vencer apartados, recordar citas)
set -e

# Railway monta el volumen de fotos como administrador (root). Arrancamos como root SOLO para
# darle ese disco al usuario "taller", y enseguida soltamos los privilegios: el sitio nunca corre como root.
if [ "$(id -u)" = "0" ]; then
  FOTOS="${RAILWAY_VOLUME_MOUNT_PATH:-/app/media}"
  mkdir -p "$FOTOS" && chown -R taller:taller "$FOTOS"
  exec setpriv --reuid=taller --regid=taller --init-groups sh "$0" "$@"
fi

if [ "$1" = "tareas" ]; then
  exec python manage.py tareas_programadas
fi

python manage.py migrate --noinput
python manage.py createcachetable

# 2 procesos atienden a la vez; si uno se queda colgado más de 30 s, se reinicia.
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 30 \
  --access-logfile - \
  --forwarded-allow-ips "*"
