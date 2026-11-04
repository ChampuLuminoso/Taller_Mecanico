# Publicar AutoPartes M&F en internet

Guía paso a paso para Jorge. Orden recomendado: **1 → 7** el primer día (el sitio queda en una
dirección de Railway), y **8 → 9** cuando compren el dominio. Precios revisados el 4 de noviembre de 2026.

| Pieza | Servicio | Costo aproximado |
|---|---|---|
| Servidor + base de datos + fotos | Railway, plan Hobby | USD 5/mes de base, más el consumo |
| Dominio (`.com`, `.com.co` o `.co`) | Cloudflare Registrar | USD 11–30 al año |
| Correos (citas, pedidos, stock) | Resend, plan gratis | USD 0 (hasta 100 al día y 3.000 al mes) |

> **¿Por qué no Gmail directo?** Railway bloquea el envío por SMTP (el método de Gmail) en el plan Hobby.
> Por eso los correos salen por Resend, que usa HTTPS. Las respuestas de los clientes sí te llegan a tu Gmail.

---

## 1. Subir el proyecto a GitHub

Railway publica desde GitHub y vuelve a publicar solo cada vez que subes un cambio.

1. Crea una cuenta en <https://github.com> si no tienes.
2. Crea un repositorio **privado** llamado `autopartes-mf` (sin README, sin .gitignore: ya los tenemos).
3. En la carpeta del proyecto:

```bash
git remote add origin https://github.com/TU_USUARIO/autopartes-mf.git
git push -u origin main --tags
```

El archivo `.env` **no** se sube (está en `.gitignore`), así que tus claves locales no salen de tu computador.

## 2. Crear el proyecto en Railway

1. Entra a <https://railway.com>, crea la cuenta con GitHub y activa el plan **Hobby**.
2. **New Project → Deploy from GitHub repo →** elige `autopartes-mf`.
3. Railway encuentra el `Dockerfile` y construye la imagen. El primer intento va a **fallar**: falta la
   base de datos y la clave secreta. Es normal; se arregla en los pasos 3 y 4.

## 3. Agregar la base de datos

En el proyecto: **New → Database → PostgreSQL**. Railway la crea y le pone sus datos de conexión.

## 4. Variables del servicio web

Abre el servicio web → pestaña **Variables** → agrega:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (así, literal: Railway lo reemplaza) |
| `DJANGO_SECRET_KEY` | Una clave larga al azar. Genérala con: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `RUTA_ADMIN` | Una dirección difícil de adivinar para tu admin, por ejemplo `taller-x7k2q9/` (con la barra al final) |
| `WHATSAPP_JEFE` | El WhatsApp del jefe con 57 adelante, por ejemplo `573001234567` |
| `URL_SITIO` | Por ahora la dirección que te da Railway (paso 5), por ejemplo `https://autopartes-mf.up.railway.app` |

No pongas `DJANGO_DEBUG`: sin ella, el sitio arranca en modo seguro (producción).

## 5. Dirección pública y revisión de salud

En el servicio web → **Settings**:

1. **Networking → Generate Domain.** Te da algo como `autopartes-mf.up.railway.app`.
2. **Deploy → Healthcheck Path:** `/salud/`. Railway entra ahí después de cada publicación; si no responde,
   deja la versión anterior funcionando.

## 6. Volumen para las fotos de los productos

Sin esto, cada vez que publiques una versión nueva **se borrarían las fotos** que subió el Jefe.

Servicio web → clic derecho → **Attach Volume** → ruta de montaje: **`/app/media`**.

El sitio detecta el volumen solo (Railway le avisa por la variable `RAILWAY_VOLUME_MOUNT_PATH`).

Ahora sí: **Deployments → Redeploy.** Al terminar, abre la dirección del paso 5: debe aparecer la tienda.

## 7. Crear tu cuenta, la de Fran y la del primer Jefe

Instala la herramienta de Railway en tu computador (<https://docs.railway.com/cli>), entra y conecta la carpeta:

```bash
railway login
railway link            # elige el proyecto autopartes-mf y el servicio web
railway ssh             # abre una consola dentro del servidor
```

Dentro de esa consola:

```bash
python manage.py crear_ingeniero --email jorgiis19@gmail.com
python manage.py crear_fran --email CORREO_DE_FRAN      # mejor si Fran escribe su propia clave
exit
```

Luego Fran entra al sitio y crea al Jefe en **Personal → Nueva cuenta**. El Jefe carga los productos
(Excel) y las fotos (**Inventario → Subir fotos**).

### Tareas de cada hora (apartados vencidos y recordatorios de citas)

1. En el proyecto: **New → GitHub Repo →** el mismo `autopartes-mf`. Ponle de nombre `tareas`.
2. **Settings → Deploy → Custom Start Command:** `sh iniciar.sh tareas`
3. **Settings → Cron Schedule:** `0 * * * *` (cada hora en punto).
4. **Variables:** las mismas del paso 4 (`DATABASE_URL`, `DJANGO_SECRET_KEY`) y, cuando las tengas, las de correo.

Cada hora libera los apartados vencidos y, desde las 5:00 p. m., envía el recordatorio de las citas de mañana
(cada cita se recuerda una sola vez). En **Logs** verás una línea como:
`2026-11-05 17:00 · apartados vencidos: 1 · recordatorios: 3`.

---

## 8. Comprar el dominio (Cloudflare)

Cloudflare vende los dominios a precio de costo (sin sobreprecio en la renovación) y además maneja el DNS,
que es lo que Railway necesita para que funcione el dominio sin `www`.

1. Crea una cuenta en <https://dash.cloudflare.com>.
2. **Domain Registration → Register Domains.** Busca el nombre. Ideas, en orden:
   - `autopartesmf.com` — el más fácil de recordar (≈ USD 11/año)
   - `autopartesmf.com.co` — muestra que es colombiano (≈ USD 15/año)
   - `autopartesmf.co` — corto, pero más caro (≈ USD 30/año)
3. Paga con tarjeta. Deja **activa la renovación automática**: si el dominio vence, el sitio y los correos dejan de funcionar.
4. Los datos del titular deben ser los del negocio (o del dueño), no los tuyos: el dominio es de ellos.

## 9. Conectar el dominio a Railway

1. En Railway, servicio web → **Settings → Networking → + Custom Domain** → escribe `autopartesmf.com`.
   Railway muestra **dos registros**: un `CNAME` y un `TXT`.
2. En Cloudflare → tu dominio → **DNS → Records → Add record**: crea esos dos registros tal cual.
   En el `CNAME` deja la nube en **gris (DNS only)**.
3. Repite para `www.autopartesmf.com` (el plan Hobby permite 2 dominios por servicio: justo estos dos).
4. Espera la marca verde en Railway (minutos, a veces hasta un par de horas). El candado HTTPS se pone solo.
5. Actualiza las variables del servicio web:
   - `DJANGO_ALLOWED_HOSTS` = `autopartesmf.com,www.autopartesmf.com`
   - `URL_SITIO` = `https://autopartesmf.com`

## 10. Correos con Resend

1. Crea la cuenta en <https://resend.com> → **Domains → Add Domain** → `autopartesmf.com`.
   Resend te da unos registros DNS (SPF y DKIM): agrégalos en Cloudflare (Resend puede hacerlo solo con
   el botón de Cloudflare). Esto evita que los correos lleguen a spam.
2. **API Keys → Create API Key** (permiso: solo enviar).
3. En Railway, en **los dos servicios** (web y tareas), agrega:

| Variable | Valor |
|---|---|
| `RESEND_API_KEY` | la llave que empieza por `re_` |
| `DEFAULT_FROM_EMAIL` | `AutoPartes M&F <avisos@autopartesmf.com>` |
| `CORREO_RESPUESTA` | `jorgiis19@gmail.com` (pendiente cambiarlo por el del taller) |

4. Prueba: agenda una cita de prueba. Te debe llegar el correo de confirmación y, a los jefes, el aviso.

## 11. Después de una semana sin problemas

Sube la protección HTTPS a su nivel completo (el navegador recordará por un año que el sitio es solo seguro):

| Variable | Valor |
|---|---|
| `DJANGO_HSTS_SEGUNDOS` | `31536000` |
| `DJANGO_HSTS_COMPLETO` | `1` |

No lo hagas antes: si algo del dominio quedara mal configurado, los visitantes no podrían entrar durante un año.

---

## Copias de seguridad

- Railway → servicio **Postgres → Backups**: activa las copias automáticas.
- Lo mismo para el **volumen** de fotos.
- Una vez al mes, descarga una copia a tu computador:
  `railway connect Postgres` y luego `pg_dump` (o desde la pestaña Backups).

## Publicar cambios

```bash
git add -A && git commit -m "Describe el cambio" && git push
```

Railway construye la nueva versión, aplica los cambios de la base de datos (`migrate`) y, solo si
`/salud/` responde, reemplaza la versión anterior. Si algo sale mal, en **Deployments** puedes volver a
la versión anterior con un clic.

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| La publicación falla con "Falta DJANGO_SECRET_KEY" | No agregaste la variable del paso 4 |
| "Bad Request (400)" al abrir el dominio | El dominio no está en `DJANGO_ALLOWED_HOSTS` |
| Error al enviar un formulario ("CSRF") | Igual: falta el dominio en `DJANGO_ALLOWED_HOSTS` |
| Las fotos desaparecen al publicar | No se montó el volumen en `/app/media` (paso 6) |
| No llegan correos | Falta `RESEND_API_KEY` en ese servicio, o el dominio no está verificado en Resend |
| Demasiadas redirecciones | En Cloudflare la nube está naranja con SSL "Flexible": ponla gris, o SSL "Full" |
