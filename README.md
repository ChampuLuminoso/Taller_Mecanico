# AutoPartes M&F · Taller Mecánico Francois · Plataforma web

Fases 1 a 7: modelo de datos, autenticación y roles, inventario y apartados, agenda de citas, tienda y pedidos, reportes, diseño de marca. Django 5.2 + PostgreSQL 16.

## Instalar en tu computador

```bash
# 1. Entorno virtual
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. PostgreSQL (una sola vez, en psql como superusuario)
CREATE USER taller PASSWORD 'taller' CREATEDB;
CREATE DATABASE taller_francois OWNER taller;

# 3. Crear las tablas y los datos iniciales (roles, 3 bahías, horario, tipos de visita)
python manage.py migrate

# 4. Probar que todas las reglas funcionan (125 pruebas)
python manage.py test

# 5. Tu cuenta de Ingeniero (pide la contraseña sin mostrarla)
python manage.py crear_ingeniero --email tu@correo.co

# 6. Arrancar
python manage.py runserver
```

| Dirección | Para qué |
|---|---|
| http://localhost:8000/ | Tienda pública (precio y stock sin registrarse) |
| http://localhost:8000/carrito/ | Carrito (funciona sin cuenta) |
| http://localhost:8000/mis-pedidos/ | Cliente: sus pedidos |
| http://localhost:8000/panel/pedidos/ | Taller: confirmar, alistar, despachar y entregar |
| http://localhost:8000/panel/ventas/ | Jefe y Fran: ventas de hoy, semana o mes + Excel |
| http://localhost:8000/panel/clientes/ | Jefe y Fran: historial por nombre, cédula o teléfono |
| http://localhost:8000/panel/auditoria/ | Jefe: auditoría general · Fran: todo |
| http://localhost:8000/cuenta/registro/ | Registro de clientes |
| http://localhost:8000/cuenta/entrar/ | Inicio de sesión (todos) |
| http://localhost:8000/cuenta/panel/ | Panel según el rol |
| http://localhost:8000/cuenta/personal/ | Crear y bloquear personal |
| http://localhost:8000/panel/inventario/ | Inventario, edición rápida, historial |
| http://localhost:8000/panel/inventario/importar/ | Cargar productos desde Excel (Jefe) |
| http://localhost:8000/panel/apartados/solicitudes/ | Aprobar o rechazar solicitudes |
| http://localhost:8000/panel/apartados/ | Entregar o cancelar apartados |
| http://localhost:8000/citas/ | Cliente: mis citas, agendar, cambiar, cancelar |
| http://localhost:8000/panel/agenda/ | Taller: agenda del día por bahía |
| http://localhost:8000/panel/agenda/bloqueos/ | Subjefe/Jefe: cerrar días o bloquear horas |
| http://localhost:8000/mantenimiento-tecnico/ | Admin de Django (solo Ingeniero) |

## Cuentas que solo se crean por consola

```bash
python manage.py crear_ingeniero --email tu@correo.co
python manage.py crear_fran --email correo@fran.co     # una sola vez; mejor que Fran escriba su clave
```

Después, Fran (o tú, en pruebas) crea el primer Jefe desde **Personal → Nueva cuenta**.

## Quién crea y bloquea a quién

| Acción | Empleado | Subjefe | Jefe | Fran |
|---|---|---|---|---|
| Crear empleados | – | ✔ | ✔ | ✔ |
| Crear subjefes | – | – | ✔ | ✔ |
| Crear jefes | – | – | – | ✔ |
| Bloquear / desbloquear | – | – | rango menor | todos |
| Aprobar / cancelar apartados | – | ✔ | ✔ | ✔ |
| Entregar apartados | ✔ | ✔ | ✔ | ✔ |
| Crear y editar productos | – | ✔ | ✔ | ✔ |
| Entradas, ajustes, cargar Excel | – | – | ✔ | ✔ |
| Correo de stock mínimo | – | – | ✔ | ✔ |
| Confirmar / cancelar pedidos | – | ✔ | ✔ | ✔ |
| Ventas, ganancias, Excel, historial de clientes | – | – | ✔ | ✔ |
| Auditoría | – | – | general | todo |
| Alistar, despachar y entregar pedidos | ✔ | ✔ | ✔ | ✔ |

## Mapa del proyecto

| Carpeta | Qué contiene |
|---|---|
| `cuentas/` | Usuarios, roles, Fran oculto, clientes (mayoría de edad, Ley 1581), empleados, auditoría |
| `cuentas/permisos.py` | Matriz de permisos: quién puede hacer qué |
| `inventario/` | Productos, historial de movimientos, solicitudes de apartado y apartados |
| `inventario/servicios.py` | Única puerta para cambiar cantidades |
| `citas/` | Agenda, 3 bahías, horario, festivos colombianos, bloqueos |
| `pedidos/` | Pedidos con contra entrega o pago en tienda, envíos en Bogotá |

## Reglas que garantiza la base de datos (no solo el código)

- Un solo usuario Fran (`un_solo_fran`).
- Lo apartado nunca supera lo físico (`apartado_no_supera_fisico`).
- Dos citas activas no se cruzan en la misma bahía (`cita_sin_cruce_por_bahia`).
- El total de un pedido siempre cuadra (`total_cuadra`).
- Auditoría e historial de inventario solo admiten inserciones (triggers).

## Diseño (Fase 7)

- Identidad tomada del logo de AutoPartes M&F: naranja de la carrocería, blanco, gris carbón y el gris salvia del fondo.
  Botones y enlaces usan un naranja un poco más hondo (`#c4501f`) para que el texto blanco se lea bien (4,65:1).
- Nombre y subtítulo configurables con `MARCA_NOMBRE` y `MARCA_SUBTITULO` (por defecto "AutoPartes M&F" / "Taller Mecánico Francois").
- Fondo con la marca de agua moviéndose lento en diagonal; guiño del logo en la esquina de cada foto de producto.
- Fuentes Barlow y Barlow Condensed servidas desde `static/fuentes` (licencia OFL incluida).
- Navegación deslizante entre secciones (View Transitions) en el sitio y en el panel, y gesto de deslizar en celular.
  El orden de las secciones sale del menú de cada rol (`cuentas/navegacion.py`). Con "reducir movimiento" activado
  en el celular o el computador, no hay deriva ni deslizamiento: solo un fundido corto.

## Reportes

- Una venta es un pedido **confirmado** (el inventario ya salió) y no cancelado; cuenta el día en que se confirmó.
- Por defecto se ve **hoy**; también semana (lunes a domingo) y mes, con comparación contra el periodo anterior.
- Productos ordenados por precio de mayor a menor (o más vendidos, o mayor ingreso). Ganancia = precio − costo guardados el día de la venta.
- Solo Jefe y Fran ven ventas, ganancias e historial de clientes.
- Solo cuenta lo que se vende por la aplicación: las ventas a mano con recibo en el taller no entran (decisión de los dueños). Exporte a Excel con hojas Resumen, Productos y Pedidos.

## Reglas de la tienda

- Cualquiera ve precios y unidades disponibles. Para comprar o solicitar un apartado hay que registrarse; el carrito se conserva al entrar.
- Domicilio solo en Bogotá: $2.000 fijo (`COSTO_ENVIO`), pago contra entrega. Recoger en el taller es gratis y se puede pagar allá.
- Entregas principalmente los sábados; la hora se coordina por teléfono (`TEXTO_ENTREGAS`).
- El pedido llega **por confirmar** y no descuenta nada. Al confirmarlo (Subjefe o Jefe) se descuenta el inventario, todo o nada.
- Empleados: alistar, "salió a entrega" y "entregado y pagado". Cancelar después de confirmar devuelve las unidades al inventario.

## Reglas de la agenda

- Horario: lunes a viernes 8:00 a. m.–6:00 p. m., sábado 9:00 a. m.–4:00 p. m.; almuerzo 1:00–2:00 p. m. (ninguna cita lo cruza).
- 3 bahías = 3 vehículos a la vez. La cita queda **confirmada** al agendar y se avisa por correo a Jefes y Fran.
- Cliente: agenda con mínimo 3 horas y máximo 20 días de anticipación; cambia o cancela hasta 4 horas antes; máximo 3 citas próximas.
- Personal: agenda sin el mínimo de 3 horas (clientes que llegan o llaman); cancela con motivo y el cliente recibe un correo.
- Todo se ajusta en `config/settings.py` → `TALLER` y en el admin (horario, tipos de visita y duraciones).

## Tareas programadas (cuando haya servidor)

```bash
python manage.py vencer_apartados    # cada noche, ~11:55 p. m.
python manage.py recordar_citas      # cada tarde, ~5:00 p. m. (citas de mañana)
```

## Correo

En desarrollo, los correos (alertas de stock) se imprimen en la terminal donde corre `runserver`.
En producción se configuran `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`,
`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `DEFAULT_FROM_EMAIL` como variables de entorno.

## Mantenimiento anual

`pip install -U holidays` cada diciembre: los festivos cambian por ley.
