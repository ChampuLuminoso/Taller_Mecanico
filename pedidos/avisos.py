from django.conf import settings
from django.urls import reverse

from cuentas.notificar import correos_con_permiso, enviar
from inventario.templatetags.taller import pesos

from .models import Pedido


def _url(nombre, *args):
    return settings.TALLER["URL_SITIO"].rstrip("/") + reverse(nombre, args=args)


def _detalle(p):
    lineas = [f"  {i.cantidad} × {i.nombre_producto} ({i.sku}) · {pesos(i.subtotal)}" for i in p.items.all()]
    lineas.append(f"  Subtotal: {pesos(p.subtotal)}")
    if p.costo_envio:
        lineas.append(f"  Envío: {pesos(p.costo_envio)}")
    lineas.append(f"  Total: {pesos(p.total)} · {p.get_metodo_pago_display()}")
    return lineas


def a_taller(pedido_id):
    p = Pedido.objects.select_related("cliente").get(pk=pedido_id)
    tel = "".join(c for c in p.telefono_contacto if c.isdigit())[-10:]
    cuerpo = [f"Nuevo pedido #{p.pk} por confirmar · {p.get_modalidad_display()}", "",
              f"Cliente: {p.cliente}", f"Celular: {p.telefono_contacto} · WhatsApp: https://wa.me/57{tel}"]
    if p.direccion_texto:
        cuerpo.append(f"Dirección: {p.direccion_texto}")
    if p.nota_cliente:
        cuerpo.append(f"Nota: {p.nota_cliente}")
    cuerpo += ["", *_detalle(p), "", "El inventario se descuenta cuando lo confirmes:", _url("pedidos:detalle_taller", p.pk)]
    return enviar(f"Nuevo pedido #{p.pk} · {pesos(p.total)}", "\n".join(cuerpo),
                  copia_oculta=correos_con_permiso("pedidos.alertas_correo"))


TEXTOS = {
    "recibido": ("Recibimos tu pedido", "Recibimos tu pedido. El taller lo revisará y te confirmará pronto."),
    "confirmado": ("Pedido confirmado", "Tu pedido fue confirmado y lo estamos alistando."),
    "listo_recoger": ("Tu pedido está listo", "Tu pedido está listo para recoger en el taller."),
    "en_camino": ("Tu pedido va en camino", "Tu pedido salió a entrega. Ten listo el pago contra entrega."),
    "cancelado": ("Pedido cancelado", "Tu pedido fue cancelado."),
}


def a_cliente(pedido_id, evento):
    p = Pedido.objects.select_related("cliente").get(pk=pedido_id)
    if not p.cliente.email:
        return False
    asunto, texto = TEXTOS[evento]
    cuerpo = [f"Hola, {p.cliente.nombres}.", "", texto]
    if evento == "cancelado" and p.motivo_cancelacion:
        cuerpo.append(f"Motivo: {p.motivo_cancelacion}")
    if evento in ("recibido", "confirmado") and p.modalidad == Pedido.ENVIO:
        cuerpo += ["", settings.TALLER["TEXTO_ENTREGAS"]]
    cuerpo += ["", f"Pedido #{p.pk}:", *_detalle(p), "", f"Ver tus pedidos: {_url('pedidos:mis_pedidos')}",
               "", f"{settings.MARCA['NOMBRE']} · {settings.MARCA['SUBTITULO']}"]
    return enviar(f"{asunto} (#{p.pk})", "\n".join(cuerpo), para=[p.cliente.email])
