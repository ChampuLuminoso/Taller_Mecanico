"""
Matriz de permisos. Es la ÚNICA fuente de verdad sobre quién puede hacer qué.
Toda vista y todo servicio llama a `requiere_permiso()` en el servidor;
ocultar un botón en la pantalla es solo comodidad, no seguridad.
"""
from django.core.exceptions import PermissionDenied

CLIENTE = {
    "tienda.comprar",
    "apartados.solicitar",
    "citas.agendar_propia",
}

EMPLEADO = {
    "inventario.ver",
    "inventario.vender",         # ventas de mostrador (se usa en la Fase 5)
    "apartados.gestionar",       # contactar al cliente, entregar apartados ya aprobados
    "pedidos.gestionar",         # ver pedidos, alistarlos y despacharlos
    "pedidos.entregar",          # marcar entregado y pagado
    "citas.gestionar",
    "clientes.ver_basico",       # nombre y teléfono para atender
}

SUBJEFE = EMPLEADO | {
    "inventario.editar",         # crear/editar/desactivar productos (sin tocar cantidades)
    "apartados.aprobar",         # decidir sobre solicitudes de apartado
    "pedidos.confirmar",         # confirmar (descuenta inventario) o cancelar pedidos
    "pedidos.alertas_correo",    # aviso de pedidos nuevos por correo
    "agenda.bloquear",
    "personal.ver",
    "personal.crear_empleado",   # Subjefe y Jefe crean empleados
}

JEFE = SUBJEFE | {
    "contabilidad.ver",          # ganancias (revela el costo de los productos)
    "reportes.ver",              # ventas del día, semana y mes: solo Jefe y Fran
    "reportes.exportar",
    "clientes.ver_historial",    # historial de compras de cada cliente
    "usuarios.gestionar",        # bloquear, desbloquear, anonimizar
    "personal.crear_subjefe",    # solo el Jefe crea subjefes
    "auditoria.ver",             # auditoría general (sin las acciones de Fran)
    "inventario.entrada",        # solo el Jefe registra mercancía que llega
    "inventario.ajustar",        # correcciones de conteo
    "inventario.importar",       # carga masiva desde Excel
    "inventario.alertas_correo", # recibe el correo de stock mínimo
    "citas.alertas_correo",      # recibe aviso de citas nuevas, cambios y cancelaciones
}

# El Ingeniero mantiene la plataforma, pero NO necesita ver ventas ni datos de clientes.
INGENIERO = {
    "sistema.mantenimiento",
    "sistema.ver_errores",
    "sistema.respaldos",
}

FRAN = JEFE | INGENIERO | {
    "auditoria.ver_total",       # incluye lo que hacen los jefes, en todo momento
    "contabilidad.ver_total",
    "acciones.anular",           # revertir decisiones de jefes (queda en su auditoría privada)
    "personal.crear_jefe",       # un Jefe no puede crear otro Jefe; Fran sí
}

# Qué permiso hace falta para crear una cuenta de cada rol de personal.
# El Ingeniero no aparece: se crea solo por consola (comando crear_ingeniero).
CREAR_ROL = {
    "EMPLEADO": "personal.crear_empleado",
    "SUBJEFE": "personal.crear_subjefe",
    "JEFE": "personal.crear_jefe",
}

# Jerarquía para bloquear: solo se bloquea a alguien de rango MENOR al propio.
RANGO = {"CLIENTE": 0, "EMPLEADO": 1, "SUBJEFE": 2, "JEFE": 3, "INGENIERO": 3}


def rango_de(usuario) -> int:
    if usuario.es_fran:
        return 99
    return max((RANGO.get(c, 0) for c in usuario.codigos_rol()), default=0)

POR_ROL = {
    "CLIENTE": CLIENTE,
    "EMPLEADO": EMPLEADO,
    "SUBJEFE": SUBJEFE,
    "JEFE": JEFE,
    "INGENIERO": INGENIERO,
}


def permisos_de(usuario) -> set[str]:
    if not usuario or not usuario.is_authenticated or not usuario.puede_entrar:
        return set()
    if usuario.es_fran:
        return set(FRAN)
    permisos: set[str] = set()
    for codigo in usuario.codigos_rol():
        permisos |= POR_ROL.get(codigo, set())
    return permisos


def tiene_permiso(usuario, permiso: str) -> bool:
    return permiso in permisos_de(usuario)


def requiere_permiso(usuario, permiso: str) -> None:
    if not tiene_permiso(usuario, permiso):
        raise PermissionDenied(f"No tienes permiso para: {permiso}")
