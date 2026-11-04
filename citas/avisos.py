"""Correos de la agenda: a los jefes (con los datos para contactar al cliente) y al cliente."""
from django.conf import settings
from django.urls import reverse
from django.utils import formats, timezone

from cuentas.notificar import correos_con_permiso, enviar

from .models import Cita

EVENTOS = {
    "nueva": "Nueva cita",
    "reprogramada": "Cita reprogramada",
    "cancelada": "Cita cancelada",
}


def hora_co(dt):
    """2:30 p. m. — como se escribe la hora en Colombia."""
    local = timezone.localtime(dt)
    return f"{local.hour % 12 or 12}:{local:%M} {'a. m.' if local.hour < 12 else 'p. m.'}"


def _cuando(dt):
    return formats.date_format(timezone.localtime(dt), "l j \\d\\e F").lower() + " a las " + hora_co(dt)


def _url(nombre, *args):
    return settings.TALLER["URL_SITIO"].rstrip("/") + reverse(nombre, args=args)


def a_jefes(cita_id, evento, detalle=""):
    cita = Cita.objects.select_related("cliente", "vehiculo", "tipo_visita", "bahia").get(pk=cita_id)
    c = cita.cliente
    telefono = "".join(ch for ch in c.telefono if ch.isdigit())
    lineas = [
        f"{EVENTOS[evento]}: {cita.tipo_visita.nombre}",
        f"Cuándo: {_cuando(cita.inicio)} ({cita.tipo_visita.duracion_min} min, {cita.bahia})",
        "",
        f"Cliente: {c}",
        f"Celular: {c.telefono}  ·  WhatsApp: https://wa.me/57{telefono[-10:]}",
    ]
    if c.email:
        lineas.append(f"Correo: {c.email}")
    if cita.vehiculo:
        lineas.append(f"Vehículo: {cita.vehiculo}")
    if cita.nota_cliente:
        lineas += ["", f"Lo que cuenta el cliente: {cita.nota_cliente}"]
    if detalle:
        lineas += ["", detalle]
    lineas += ["", f"Agenda del día: {_url('citas:agenda')}?fecha={timezone.localtime(cita.inicio):%Y-%m-%d}"]
    return enviar(f"{EVENTOS[evento]} · {_cuando(cita.inicio)}", "\n".join(lineas),
                  copia_oculta=correos_con_permiso("citas.alertas_correo"))


def a_cliente(cita_id, evento, detalle=""):
    cita = Cita.objects.select_related("cliente", "tipo_visita").get(pk=cita_id)
    if not cita.cliente.email:
        return False
    textos = {
        "nueva": "Tu cita quedó confirmada.",
        "reprogramada": "Tu cita cambió de horario. Esta es la nueva hora.",
        "cancelada": "Tu cita fue cancelada.",
        "recordatorio": "Te recordamos tu cita de mañana.",
    }
    limite = settings.TALLER["CITAS_LIMITE_CAMBIO_HORAS"]
    lineas = [f"Hola, {cita.cliente.nombres}.", "", textos[evento], "",
              f"{cita.tipo_visita.nombre}: {_cuando(cita.inicio)}"]
    if detalle:
        lineas += ["", detalle]
    if evento != "cancelada":
        lineas += ["", f"Si necesitas cancelar o cambiar la hora, hazlo desde tu cuenta hasta {limite} horas antes:",
                   _url("citas:mis_citas")]
    lineas += ["", "Taller Mecánico Francois"]
    asunto = {"recordatorio": "Recordatorio de tu cita"}.get(evento, textos[evento].rstrip("."))
    return enviar(asunto, "\n".join(lineas), para=[cita.cliente.email])
