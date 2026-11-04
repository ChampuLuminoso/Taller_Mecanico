"""
Toda operación que cambia cantidades pasa por aquí.

`transaction.atomic()` + `select_for_update()` = si dos personas venden la
última unidad al mismo tiempo, la segunda espera a la primera y luego ve que
ya no hay stock. Nunca quedan cantidades negativas ni historiales descuadrados.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from citas.calendario import sumar_dias_habiles
from cuentas.auditoria import registrar
from cuentas.permisos import requiere_permiso

from . import alertas
from .models import Apartado, MovimientoInventario as M, Producto, SolicitudApartado

# Cómo afecta cada tipo a (físico, apartado), por unidad.
EFECTO = {
    M.ENTRADA: (+1, 0),
    M.DEVOLUCION: (+1, 0),
    M.VENTA: (-1, 0),
    M.APARTADO: (0, +1),
    M.LIBERACION: (0, -1),
    M.ENTREGA_APARTADO: (-1, -1),
}


@transaction.atomic
def mover(producto_id, tipo, cantidad, usuario, motivo, referencia="", ajuste_signo=+1):
    """Registra un movimiento. Para AJUSTE usa ajuste_signo=+1 (sobró) o −1 (faltó)."""
    if not motivo or not motivo.strip():
        raise ValidationError("Todo movimiento necesita un motivo.")
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")

    producto = Producto.objects.select_for_update().get(pk=producto_id)

    if tipo == M.AJUSTE:
        df, da = ajuste_signo * cantidad, 0
    else:
        uf, ua = EFECTO[tipo]
        df, da = uf * cantidad, ua * cantidad

    nueva_f = producto.cantidad_fisica + df
    nueva_a = producto.cantidad_apartada + da
    if nueva_f < 0:
        raise ValidationError(f"No hay suficiente stock de {producto.sku} (hay {producto.cantidad_fisica}).")
    if nueva_a < 0 or nueva_a > nueva_f:
        raise ValidationError(f"No hay suficientes unidades disponibles de {producto.sku} (disponibles: {producto.disponible}).")

    disponible_antes = producto.disponible
    producto.cantidad_fisica, producto.cantidad_apartada = nueva_f, nueva_a
    producto.save(update_fields=["cantidad_fisica", "cantidad_apartada", "actualizado_en"])

    # Solo se avisa al CRUZAR el mínimo (no en cada venta posterior), y solo si la transacción
    # termina bien: on_commit espera a que todo se guarde antes de enviar el correo.
    if producto.activo and disponible_antes > producto.stock_minimo >= producto.disponible:
        transaction.on_commit(lambda: alertas.avisar_stock_minimo(producto.pk))

    return M.objects.create(
        producto=producto, tipo=tipo, delta_fisica=df, delta_apartada=da,
        saldo_fisica=nueva_f, saldo_apartada=nueva_a,
        motivo=motivo.strip(), referencia=referencia, usuario=usuario,
    )


def registrar_entrada(producto_id, cantidad, usuario, motivo):
    requiere_permiso(usuario, "inventario.entrada")
    return mover(producto_id, M.ENTRADA, cantidad, usuario, motivo)


def ajustar(producto_id, cantidad, signo, usuario, motivo):
    requiere_permiso(usuario, "inventario.ajustar")
    return mover(producto_id, M.AJUSTE, cantidad, usuario, motivo, ajuste_signo=signo)


# ───────────────────────── Apartados ─────────────────────────

def solicitar_apartado(cliente, producto, cantidad, nota, usuario):
    """El cliente pide desde la web. No descuenta nada todavía."""
    requiere_permiso(usuario, "apartados.solicitar")
    if not producto.activo:
        raise ValidationError("Este producto no está disponible.")
    return SolicitudApartado.objects.create(cliente=cliente, producto=producto,
                                            cantidad=cantidad, nota_cliente=nota)


def _vencimiento(abono, desde=None):
    cfg = settings.TALLER
    dias = cfg["DIAS_VENCE_APARTADO_ABONO"] if abono and abono > 0 else cfg["DIAS_VENCE_APARTADO"]
    return sumar_dias_habiles(desde or timezone.now(), dias)


@transaction.atomic
def crear_apartado(producto, cliente, cantidad, usuario, abono=0, nota="", solicitud=None):
    requiere_permiso(usuario, "apartados.aprobar")
    apartado = Apartado.objects.create(
        producto=producto, cliente=cliente, cantidad=cantidad, abono=abono, nota=nota,
        solicitud=solicitud, vence_en=_vencimiento(abono), creado_por=usuario,
    )
    mover(producto.pk, M.APARTADO, cantidad, usuario, "Apartado para cliente", f"apartado:{apartado.pk}")
    registrar(usuario, "crear_apartado", "Apartado", apartado.pk,
              despues={"producto": producto.sku, "cantidad": cantidad, "abono": str(abono)})
    return apartado


@transaction.atomic
def responder_solicitud(solicitud_id, usuario, aprobar: bool, respuesta="", abono=0):
    requiere_permiso(usuario, "apartados.aprobar")
    solicitud = SolicitudApartado.objects.select_for_update().get(pk=solicitud_id)
    if solicitud.estado != SolicitudApartado.PENDIENTE:
        raise ValidationError("Esta solicitud ya fue respondida.")
    solicitud.revisada_por, solicitud.revisada_en, solicitud.respuesta = usuario, timezone.now(), respuesta
    apartado = None
    if aprobar:
        apartado = crear_apartado(solicitud.producto, solicitud.cliente, solicitud.cantidad,
                                  usuario, abono=abono, solicitud=solicitud)
        solicitud.estado = SolicitudApartado.APROBADA
    else:
        solicitud.estado = SolicitudApartado.RECHAZADA
    solicitud.save()
    registrar(usuario, "responder_solicitud_apartado", "SolicitudApartado", solicitud.pk,
              despues={"estado": solicitud.estado, "respuesta": respuesta})
    return apartado


@transaction.atomic
def cerrar_apartado(apartado_id, usuario, nuevo_estado, motivo=""):
    """ENTREGADO: el producto sale del taller. CANCELADO/VENCIDO: vuelve a estar disponible."""
    apartado = Apartado.objects.select_for_update().get(pk=apartado_id)
    if apartado.estado != Apartado.ACTIVO:
        raise ValidationError("El apartado ya está cerrado.")
    if nuevo_estado == Apartado.ENTREGADO:
        requiere_permiso(usuario, "apartados.gestionar")
        mover(apartado.producto_id, M.ENTREGA_APARTADO, apartado.cantidad, usuario,
              motivo or "Entrega de apartado", f"apartado:{apartado.pk}")
    elif nuevo_estado in (Apartado.CANCELADO, Apartado.VENCIDO):
        if nuevo_estado == Apartado.CANCELADO:
            requiere_permiso(usuario, "apartados.aprobar")
        mover(apartado.producto_id, M.LIBERACION, apartado.cantidad, usuario,
              motivo or f"Apartado {nuevo_estado.lower()}", f"apartado:{apartado.pk}")
    else:
        raise ValidationError("Estado de cierre inválido.")
    apartado.estado, apartado.cerrado_en = nuevo_estado, timezone.now()
    apartado.save(update_fields=["estado", "cerrado_en"])
    return apartado


def vencer_apartados(usuario_sistema, ahora=None):
    """Tarea nocturna: libera los apartados que pasaron su fecha."""
    ahora = ahora or timezone.now()
    vencidos = list(Apartado.objects.filter(estado=Apartado.ACTIVO, vence_en__lt=ahora)
                    .values_list("pk", flat=True))
    for pk in vencidos:
        cerrar_apartado(pk, usuario_sistema, Apartado.VENCIDO, "Vencimiento automático")
    return len(vencidos)
