"""
Ciclo de vida de un pedido:

  RECIBIDO ──confirmar (Subjefe/Jefe)──► CONFIRMADO ─► ALISTADO ─► EN_CAMINO ─► ENTREGADO
     │            descuenta inventario         (empleados)     (solo envío)    (se cobra)
     └─► CANCELADO (cliente o Subjefe/Jefe)     cualquier estado antes de ENTREGADO
                                                 ─► CANCELADO (devuelve al inventario)

El pedido RECIBIDO no aparta nada: hasta que el taller confirma, el producto
sigue disponible para otros clientes (igual que con las solicitudes de apartado).
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from cuentas.auditoria import registrar
from cuentas.permisos import requiere_permiso, tiene_permiso
from inventario.models import MovimientoInventario as M, Producto
from inventario.servicios import mover

from . import avisos
from .models import Pedido, PedidoItem

P = Pedido


def _texto_direccion(d):
    partes = [d.direccion, d.barrio, d.localidad, d.ciudad]
    texto = ", ".join(p for p in partes if p)
    return f"{texto} ({d.indicaciones})" if d.indicaciones else texto


@transaction.atomic
def crear_pedido(usuario, cliente, lineas, *, modalidad, metodo_pago, telefono, direccion=None, nota=""):
    """`lineas`: lista de (producto_id, cantidad). Precios y nombres se leen de la base de datos."""
    requiere_permiso(usuario, "tienda.comprar")
    if getattr(usuario, "cliente", None) != cliente:
        raise PermissionDenied("Solo puedes hacer pedidos a tu nombre.")
    if not lineas:
        raise ValidationError("Tu carrito está vacío.")
    if modalidad not in dict(P.MODALIDADES) or metodo_pago not in dict(P.METODOS_PAGO):
        raise ValidationError("Modalidad o método de pago inválido.")
    if modalidad == P.ENVIO:
        if direccion is None or direccion.cliente_id != cliente.pk:
            raise ValidationError("Elige la dirección de entrega.")
        if metodo_pago != P.CONTRA_ENTREGA:
            raise ValidationError("Los domicilios se pagan contra entrega.")

    productos = {p.pk: p for p in Producto.objects.filter(pk__in=[pid for pid, _ in lineas])}
    items, problemas = [], []
    for pid, cantidad in lineas:
        p = productos.get(int(pid))
        if p is None or not p.activo:
            problemas.append("Un producto del carrito ya no está a la venta.")
        elif cantidad < 1:
            continue
        elif cantidad > p.disponible:
            problemas.append(f"De {p.nombre} solo hay {p.disponible} disponible(s).")
        else:
            items.append(PedidoItem(producto=p, sku=p.sku, nombre_producto=p.nombre, cantidad=cantidad,
                                    precio_unitario=p.precio_venta, costo_unitario=p.costo,
                                    iva_pct=p.iva_pct))
    if problemas:
        raise ValidationError(problemas)

    subtotal = sum((i.precio_unitario * i.cantidad for i in items), Decimal(0))
    iva = sum((i.precio_unitario * i.cantidad * i.iva_pct / 100 for i in items), Decimal(0)).quantize(Decimal("1"))
    envio = Decimal(settings.TALLER["COSTO_ENVIO"]) if modalidad == P.ENVIO else Decimal(0)
    pedido = Pedido.objects.create(
        cliente=cliente, modalidad=modalidad, metodo_pago=metodo_pago, telefono_contacto=telefono,
        direccion=direccion if modalidad == P.ENVIO else None,
        direccion_texto=_texto_direccion(direccion) if modalidad == P.ENVIO else "",
        subtotal=subtotal, iva=iva, costo_envio=envio, total=subtotal + iva + envio, nota_cliente=nota.strip(),
    )
    for i in items:
        i.pedido = pedido
    PedidoItem.objects.bulk_create(items)
    registrar(usuario, "crear_pedido", "Pedido", pedido.pk, despues={"total": str(pedido.total), "items": len(items)})
    transaction.on_commit(lambda: (avisos.a_taller(pedido.pk), avisos.a_cliente(pedido.pk, "recibido")))
    return pedido


def _bloquear(pedido_id):
    return Pedido.objects.select_for_update().select_related("cliente").get(pk=pedido_id)


@transaction.atomic
def confirmar(pedido_id, usuario):
    """Descuenta el inventario. Si algo ya no alcanza, NO se confirma nada (todo o nada)."""
    requiere_permiso(usuario, "pedidos.confirmar")
    pedido = _bloquear(pedido_id)
    if pedido.estado != P.RECIBIDO:
        raise ValidationError("Este pedido ya fue procesado.")
    for item in pedido.items.select_related("producto"):
        mover(item.producto_id, M.VENTA, item.cantidad, usuario, "Venta en tienda web", f"pedido:{pedido.pk}")
    pedido.estado, pedido.confirmado_por, pedido.confirmado_en = P.CONFIRMADO, usuario, timezone.now()
    pedido.save(update_fields=["estado", "confirmado_por", "confirmado_en"])
    registrar(usuario, "confirmar_pedido", "Pedido", pedido.pk, despues={"total": str(pedido.total)})
    transaction.on_commit(lambda: avisos.a_cliente(pedido.pk, "confirmado"))
    return pedido


@transaction.atomic
def avanzar(pedido_id, usuario, nuevo_estado):
    """Pasos de logística que hacen los empleados: alistar, despachar y entregar."""
    pedido = _bloquear(pedido_id)
    reglas = {
        P.ALISTADO: ("pedidos.gestionar", [P.CONFIRMADO]),
        P.EN_CAMINO: ("pedidos.gestionar", [P.CONFIRMADO, P.ALISTADO]),
        P.ENTREGADO: ("pedidos.entregar", [P.EN_CAMINO] if pedido.modalidad == P.ENVIO else [P.CONFIRMADO, P.ALISTADO]),
    }
    if nuevo_estado not in reglas:
        raise ValidationError("Paso inválido.")
    permiso, desde = reglas[nuevo_estado]
    requiere_permiso(usuario, permiso)
    if nuevo_estado == P.EN_CAMINO and pedido.modalidad != P.ENVIO:
        raise ValidationError("Este pedido se recoge en el taller: no sale a domicilio.")
    if pedido.estado not in desde:
        raise ValidationError(f"Un pedido {pedido.get_estado_display().lower()} no puede pasar a "
                              f"{dict(P.ESTADOS)[nuevo_estado].lower()}.")
    campos = ["estado"]
    pedido.estado = nuevo_estado
    if nuevo_estado == P.EN_CAMINO and hasattr(usuario, "empleado"):
        pedido.repartidor = usuario.empleado
        campos.append("repartidor")
    if nuevo_estado == P.ENTREGADO:
        # Contra entrega o en tienda: se cobra en el momento de entregar.
        pedido.entregado_en = pedido.pagado_en = timezone.now()
        pedido.pagado = True
        campos += ["entregado_en", "pagado", "pagado_en"]
    pedido.save(update_fields=campos)
    registrar(usuario, "avanzar_pedido", "Pedido", pedido.pk, despues={"estado": nuevo_estado})
    if nuevo_estado in (P.EN_CAMINO, P.ALISTADO):
        evento = "en_camino" if nuevo_estado == P.EN_CAMINO else ("listo_recoger" if pedido.modalidad == P.RECOGER else None)
        if evento:
            transaction.on_commit(lambda: avisos.a_cliente(pedido.pk, evento))
    return pedido


@transaction.atomic
def cancelar(pedido_id, usuario, motivo=""):
    pedido = _bloquear(pedido_id)
    es_dueno = getattr(usuario, "cliente", None) == pedido.cliente and tiene_permiso(usuario, "tienda.comprar")
    es_taller = tiene_permiso(usuario, "pedidos.confirmar")
    if not (es_dueno or es_taller):
        raise PermissionDenied("No puedes cancelar este pedido.")
    if pedido.estado in (P.ENTREGADO, P.CANCELADO):
        raise ValidationError("Este pedido ya está cerrado.")
    if not es_taller and pedido.estado != P.RECIBIDO:
        raise ValidationError("El taller ya confirmó tu pedido. Para cancelarlo, comunícate por WhatsApp.")
    if es_taller and not motivo.strip():
        raise ValidationError("Escribe el motivo: se le enviará al cliente.")

    if pedido.estado in P.DESCONTADOS:   # devolver al inventario lo que ya se había descontado
        for item in pedido.items.all():
            mover(item.producto_id, M.DEVOLUCION, item.cantidad, usuario,
                  "Pedido cancelado: vuelve al inventario", f"pedido:{pedido.pk}")
    pedido.estado, pedido.cancelado_por, pedido.cancelado_en = P.CANCELADO, usuario, timezone.now()
    pedido.motivo_cancelacion = (motivo.strip() or "Cancelado por el cliente")[:200]
    pedido.save(update_fields=["estado", "cancelado_por", "cancelado_en", "motivo_cancelacion"])
    registrar(usuario, "cancelar_pedido", "Pedido", pedido.pk, despues={"motivo": pedido.motivo_cancelacion})
    if es_taller and not es_dueno:
        transaction.on_commit(lambda: avisos.a_cliente(pedido.pk, "cancelado"))
    return pedido
