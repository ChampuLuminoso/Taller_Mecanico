# Demostración estática (Vercel)

Páginas ya armadas con **datos de ejemplo**. No tiene servidor, base de datos ni claves.
Los formularios no guardan nada. No incluye a Fran ni al Ingeniero.

## Publicarla en Vercel (gratis, plan Hobby)
1. Sube el proyecto a GitHub (repositorio **privado**).
2. En vercel.com → *Add New… → Project* → importa el repositorio.
3. **Root Directory**: `demo_vercel` · **Framework Preset**: `Other` · sin *Build Command* ni *Output Directory*.
4. *Deploy*. Quedará en `algo.vercel.app`. Cada `git push` la vuelve a publicar.

El sitio REAL (con base de datos, citas y pedidos) va en Railway: ver `DESPLIEGUE.md`.

## Regenerarla con los cambios nuevos
    createdb taller_demo                      # solo la primera vez
    DB_NAME=taller_demo python manage.py migrate
    DB_NAME=taller_demo python manage.py createcachetable
    DB_NAME=taller_demo python manage.py cargar_demo     # solo la primera vez
    DB_NAME=taller_demo python manage.py exportar_demo
