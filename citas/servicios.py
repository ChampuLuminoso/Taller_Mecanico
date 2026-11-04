"""
Reglas de la agenda. Todas se validan aquí, en el servidor:

- Día laboral (festivos, domingos y días cerrados por el taller no cuentan).
- Dentro del horario y sin cruzar el almuerzo (1–2 p. m.).
- Cliente: mínimo 3 horas antes y máximo 20 días hacia adelante.
  El personal puede agendar con menos anticipación (cliente que llega o llama).
- Cliente: cancela o cambia su cita hasta 4 horas antes. El personal, cuando sea necesario.
- Una bahía libre (3 vehículos a la vez). La base de datos impide el cruce aunque
  dos clientes pidan la misma hora en el mismo segundo.

Toda cita nueva queda CONFIRMADA y avisa a los jefes por correo.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from cuentas.auditoria import registrar
from cuentas.permisos import requiere_permiso, tiene_permiso

from . import avisos
from .avisos import hora_co
from .calendario import LABORAL, info_dia
from .models import Bahia, BloqueoAgenda, Cita

CFG = settings.TALLER


# ───────────────────────── Quién puede qué ─────────────────────────

def es_personal(usuario):
    return tiene_permiso(usuario, "citas.gestionar")


def _es_su_cita(usuario, cliente):
    return getattr(usuario, "cliente", None) == cliente and tiene_permiso(usuario, "citas.agendar_propia")


def _exigir_permiso_sobre(usuario, cliente):
    if not (_es_su_cita(usuario, cliente) or es_personal(usuario)):
        raise PermissionDenied("No puedes gestionar citas de otro cliente.")


def puede_cambiar(cita, usuario, ahora=None) -> bool:
    """El cliente solo hasta 4 horas antes; el personal siempre (mientras no haya pasado)."""
    ahora = ahora or timezone.now()
    if cita.estado not in Cita.ACTIVAS or cita.inicio <= ahora:
        return False
    if es_personal(usuario):
        return True
    return cita.inicio - ahora >= timedelta(hours=CFG["CITAS_LIMITE_CAMBIO_HORAS"])


# ───────────────────────── Reglas de horario ─────────────────────────

def _cruza(inicio_a, fin_a, inicio_b, fin_b):
    return inicio_a < fin_b and fin_a > inicio_b


def _limites(personal, ahora=None):
    """Primera y última fecha-hora en que se puede agendar."""
    ahora = ahora or timezone.now()
    minimo = ahora if personal else ahora + timedelta(hours=CFG["CITAS_ANTICIPACION_MIN_HORAS"])
    ultimo_dia = timezone.localdate(ahora) + timedelta(days=CFG["CITAS_MAX_DIAS"])
    return minimo, ultimo_dia


def _almuerzo(fecha, dia):
    if not (dia.almuerzo_inicio and dia.almuerzo_fin):
        return None
    return (timezone.make_aware(datetime.combine(fecha, dia.almuerzo_inicio)),
            timezone.make_aware(datetime.combine(fecha, dia.almuerzo_fin)))


def validar_horario(inicio: datetime, duracion_min: int, personal=False):
    """Devuelve la hora de fin si el horario cumple las reglas; si no, explica por qué."""
    local = timezone.localtime(inicio)
    fin = local + timedelta(minutes=duracion_min)
    minimo, ultimo_dia = _limites(personal)

    if inicio <= timezone.now():
        raise ValidationError("No se puede agendar en el pasado.")
    if inicio < minimo:
        raise ValidationError(f"Las citas se agendan con mínimo {CFG['CITAS_ANTICIPACION_MIN_HORAS']} horas "
                              f"de anticipación.")
    if local.date() > ultimo_dia:
        raise ValidationError(f"Solo se puede agendar hasta {CFG['CITAS_MAX_DIAS']} días hacia adelante.")

    dia = info_dia(local.date())
    if dia.tipo != LABORAL:
        raise ValidationError(f"Ese día el taller no atiende ({dia.motivo}).")
    if local.time() < dia.abre or fin.time() > dia.cierra or fin.date() != local.date():
        raise ValidationError(f"El horario de ese día es de {hora_co(timezone.make_aware(datetime.combine(local.date(), dia.abre)))} "
                              f"a {hora_co(timezone.make_aware(datetime.combine(local.date(), dia.cierra)))}, "
                              f"y este servicio dura {duracion_min} minutos.")
    almuerzo = _almuerzo(local.date(), dia)
    if almuerzo and _cruza(local, fin, *almuerzo):
        raise ValidationError(f"Entre {hora_co(almuerzo[0])} y {hora_co(almuerzo[1])} es la hora de almuerzo: "
                              f"este servicio dura {duracion_min} minutos y no alcanza a terminar antes.")
    return fin


def _bloqueado(inicio, fin, bahia):
    return BloqueoAgenda.objects.filter(
        Q(bahia__isnull=True) | Q(bahia=bahia), inicio__lt=fin, fin__gt=inicio
    ).exists()


# ───────────────────────── Disponibilidad ─────────────────────────

def franjas_libres(fecha, tipo_visita, personal=False, excluir_cita=None):
    """Horas de inicio con al menos una bahía libre. Hace 4 consultas por día, no una por franja."""
    dia = info_dia(fecha)
    if dia.tipo != LABORAL:
        return []
    ahora = timezone.now()
    minimo, ultimo_dia = _limites(personal, ahora)
    if fecha > ultimo_dia:
        return []

    paso = timedelta(minutes=CFG["INTERVALO_CITAS_MIN"])
    dur = timedelta(minutes=tipo_visita.duracion_min)
    actual = timezone.make_aware(datetime.combine(fecha, dia.abre))
    cierre = timezone.make_aware(datetime.combine(fecha, dia.cierra))
    almuerzo = _almuerzo(fecha, dia)

    bahias = list(Bahia.objects.filter(activa=True))
    citas = Cita.objects.filter(estado__in=Cita.ACTIVAS, inicio__lt=cierre, fin__gt=actual)
    if excluir_cita:
        citas = citas.exclude(pk=excluir_cita.pk)
    citas = list(citas.values_list("bahia_id", "inicio", "fin"))
    bloqueos = list(BloqueoAgenda.objects.filter(inicio__lt=cierre, fin__gt=actual).values_list("bahia_id", "inicio", "fin"))

    libres = []
    while actual + dur <= cierre:
        fin = actual + dur
        if actual >= minimo and actual > ahora and not (almuerzo and _cruza(actual, fin, *almuerzo)):
            for b in bahias:
                ocupada = any(bid == b.pk and _cruza(actual, fin, i, f) for bid, i, f in citas)
                bloqueada = any(bid in (None, b.pk) and _cruza(actual, fin, i, f) for bid, i, f in bloqueos)
                if not ocupada and not bloqueada:
                    libres.append(timezone.localtime(actual))
                    break
        actual += paso
    return libres


def dias_para_calendario(tipo_visita, personal=False, excluir_cita=None):
    """Cada día de la ventana (hoy … hoy+20) con su estado, para pintar el calendario."""
    hoy = timezone.localdate()
    _, ultimo = _limites(personal)
    dias = []
    fecha = hoy
    while fecha <= ultimo:
        info = info_dia(fecha)
        if info.tipo != LABORAL:
            estado, texto = "cerrado", info.motivo or "Cerrado"
        else:
            libres = len(franjas_libres(fecha, tipo_visita, personal, excluir_cita))
            estado, texto = ("libre", f"{libres} horario{'s' if libres != 1 else ''}") if libres else ("lleno", "Sin cupos")
        dias.append({"fecha": fecha, "estado": estado, "texto": texto})
        fecha += timedelta(days=1)
    return dias


# ───────────────────────── Operaciones ─────────────────────────

def _ocupar_bahia(guardar, inicio, fin):
    """Prueba bahía por bahía. Si la base de datos dice 'cruce', pasa a la siguiente."""
    for bahia in Bahia.objects.filter(activa=True).order_by("pk"):
        if _bloqueado(inicio, fin, bahia):
            continue
        try:
            with transaction.atomic():   # punto de guardado: si choca, solo se deshace este intento
                return guardar(bahia)
        except IntegrityError:
            continue
    raise ValidationError("Ese horario se acaba de llenar. Elige otra hora.")


def agendar(cliente, tipo_visita, inicio, usuario, vehiculo=None, nota=""):
    _exigir_permiso_sobre(usuario, cliente)
    personal = es_personal(usuario)
    if not tipo_visita.activo:
        raise ValidationError("Ese tipo de visita ya no está disponible.")
    if vehiculo and vehiculo.cliente_id != cliente.pk:
        raise ValidationError("Ese vehículo no pertenece al cliente.")
    if not personal:
        activas = Cita.objects.filter(cliente=cliente, estado__in=Cita.ACTIVAS, inicio__gt=timezone.now()).count()
        if activas >= CFG["CITAS_MAX_ACTIVAS_CLIENTE"]:
            raise ValidationError(f"Ya tienes {activas} citas próximas. Para agendar otra, espera a que pase "
                                  f"alguna o comunícate con el taller.")

    fin = validar_horario(inicio, tipo_visita.duracion_min, personal)
    with transaction.atomic():
        cita = _ocupar_bahia(lambda bahia: Cita.objects.create(
            cliente=cliente, vehiculo=vehiculo, tipo_visita=tipo_visita, bahia=bahia, inicio=inicio, fin=fin,
            nota_cliente=nota.strip(), estado=Cita.CONFIRMADA, creada_por=usuario), inicio, fin)
        registrar(usuario, "agendar_cita", "Cita", cita.pk,
                  despues={"inicio": timezone.localtime(inicio).isoformat(), "tipo": tipo_visita.nombre,
                           "cliente": str(cliente), "bahia": str(cita.bahia)})
        transaction.on_commit(lambda: (avisos.a_jefes(cita.pk, "nueva"), avisos.a_cliente(cita.pk, "nueva")))
    return cita


def reprogramar(cita_id, usuario, nuevo_inicio):
    with transaction.atomic():
        cita = Cita.objects.select_for_update().select_related("cliente", "tipo_visita").get(pk=cita_id)
        _exigir_permiso_sobre(usuario, cita.cliente)
        if not puede_cambiar(cita, usuario):
            raise ValidationError(f"Solo se puede cambiar la cita hasta {CFG['CITAS_LIMITE_CAMBIO_HORAS']} horas "
                                  f"antes. Comunícate con el taller.")
        personal = es_personal(usuario)
        nuevo_fin = validar_horario(nuevo_inicio, cita.tipo_visita.duracion_min, personal)
        antes = timezone.localtime(cita.inicio)

        def mover(bahia):
            cita.inicio, cita.fin, cita.bahia = nuevo_inicio, nuevo_fin, bahia
            cita.veces_reprogramada += 1
            cita.recordatorio_enviado_en = None
            cita.save(update_fields=["inicio", "fin", "bahia", "veces_reprogramada", "recordatorio_enviado_en"])
            return cita

        _ocupar_bahia(mover, nuevo_inicio, nuevo_fin)
        registrar(usuario, "reprogramar_cita", "Cita", cita.pk, antes={"inicio": antes.isoformat()},
                  despues={"inicio": timezone.localtime(nuevo_inicio).isoformat(), "bahia": str(cita.bahia)})
        detalle = f"Antes: {antes:%d/%m/%Y} a las {hora_co(antes)}."
        transaction.on_commit(lambda: (avisos.a_jefes(cita.pk, "reprogramada", detalle),
                                       avisos.a_cliente(cita.pk, "reprogramada", detalle)))
    return cita


def cancelar(cita_id, usuario, motivo=""):
    with transaction.atomic():
        cita = Cita.objects.select_for_update().select_related("cliente").get(pk=cita_id)
        _exigir_permiso_sobre(usuario, cita.cliente)
        personal = es_personal(usuario)
        if not puede_cambiar(cita, usuario):
            raise ValidationError(f"Solo se puede cancelar hasta {CFG['CITAS_LIMITE_CAMBIO_HORAS']} horas antes. "
                                  f"Comunícate con el taller.")
        if personal and not motivo.strip():
            raise ValidationError("Escribe el motivo: se le enviará al cliente.")
        cita.estado, cita.cancelada_por, cita.cancelada_en = Cita.CANCELADA, usuario, timezone.now()
        cita.motivo_cancelacion = motivo.strip()[:200] or "Cancelada por el cliente"
        cita.save(update_fields=["estado", "cancelada_por", "cancelada_en", "motivo_cancelacion"])
        registrar(usuario, "cancelar_cita", "Cita", cita.pk, despues={"motivo": cita.motivo_cancelacion})
        quien = "el taller" if personal else "el cliente"
        detalle = f"Cancelada por {quien}. Motivo: {cita.motivo_cancelacion}"
        transaction.on_commit(lambda: avisos.a_jefes(cita.pk, "cancelada", detalle))
        if personal:   # si el cliente canceló, no hace falta escribirle a él mismo
            transaction.on_commit(lambda: avisos.a_cliente(
                cita.pk, "cancelada", f"Motivo: {cita.motivo_cancelacion}\nSi quieres, agenda otra fecha desde tu cuenta."))
    return cita


def marcar(cita_id, usuario, estado):
    """Cerrar la cita el mismo día: ATENDIDA o NO_ASISTIO."""
    requiere_permiso(usuario, "citas.gestionar")
    if estado not in (Cita.ATENDIDA, Cita.NO_ASISTIO):
        raise ValidationError("Estado inválido.")
    with transaction.atomic():
        cita = Cita.objects.select_for_update().get(pk=cita_id)
        if cita.estado not in Cita.ACTIVAS:
            raise ValidationError("Esa cita ya está cerrada.")
        if timezone.localtime(cita.inicio).date() > timezone.localdate():
            raise ValidationError("Solo se puede cerrar una cita el día que ocurre o después.")
        cita.estado = estado
        cita.save(update_fields=["estado"])
        registrar(usuario, "cerrar_cita", "Cita", cita.pk, despues={"estado": estado})
    return cita


# ───────────────────────── Bloqueos y días cerrados ─────────────────────────

def citas_afectadas(inicio, fin):
    return list(Cita.objects.filter(estado__in=Cita.ACTIVAS, inicio__lt=fin, fin__gt=inicio)
                .select_related("cliente", "tipo_visita").order_by("inicio"))


def bloquear(usuario, fecha, motivo, desde=None, hasta=None):
    """Sin horas → cierra el día entero. Con horas → bloquea esa franja para todo el taller.
    No cancela citas existentes: devuelve las afectadas para que el taller avise a cada cliente."""
    from .models import ExcepcionCalendario

    requiere_permiso(usuario, "agenda.bloquear")
    if not motivo or not motivo.strip():
        raise ValidationError("Escribe el motivo del bloqueo.")
    if fecha < timezone.localdate():
        raise ValidationError("No se pueden bloquear fechas pasadas.")
    if (desde is None) != (hasta is None):
        raise ValidationError("Para bloquear horas, escribe la hora de inicio y la de fin.")

    if desde is None:
        if ExcepcionCalendario.objects.filter(fecha=fecha).exists():
            raise ValidationError("Ese día ya tiene una excepción. Bórrala primero si quieres cambiarla.")
        obj = ExcepcionCalendario.objects.create(fecha=fecha, tipo=ExcepcionCalendario.CERRADO,
                                                 motivo=motivo.strip(), creado_por=usuario)
        inicio = timezone.make_aware(datetime.combine(fecha, datetime.min.time()))
        fin = inicio + timedelta(days=1)
    else:
        if desde >= hasta:
            raise ValidationError("La hora de fin debe ser después de la de inicio.")
        inicio = timezone.make_aware(datetime.combine(fecha, desde))
        fin = timezone.make_aware(datetime.combine(fecha, hasta))
        obj = BloqueoAgenda.objects.create(inicio=inicio, fin=fin, motivo=motivo.strip(), creado_por=usuario)
    registrar(usuario, "bloquear_agenda", type(obj).__name__, obj.pk,
              despues={"fecha": fecha.isoformat(), "desde": str(desde or ""), "hasta": str(hasta or ""),
                       "motivo": motivo.strip()})
    return obj, citas_afectadas(inicio, fin)


def quitar_bloqueo(usuario, tipo, pk):
    from .models import ExcepcionCalendario

    requiere_permiso(usuario, "agenda.bloquear")
    modelo = {"dia": ExcepcionCalendario, "horas": BloqueoAgenda}.get(tipo)
    if not modelo:
        raise ValidationError("Tipo inválido.")
    obj = modelo.objects.get(pk=pk)
    registrar(usuario, "quitar_bloqueo_agenda", modelo.__name__, pk, antes={"motivo": obj.motivo})
    obj.delete()


# ───────────────────────── Recordatorios ─────────────────────────

def enviar_recordatorios(ahora=None):
    """Citas de mañana que aún no tienen recordatorio. Se corre cada tarde."""
    ahora = ahora or timezone.now()
    manana = timezone.localdate(ahora) + timedelta(days=1)
    inicio = timezone.make_aware(datetime.combine(manana, datetime.min.time()))
    pendientes = Cita.objects.filter(estado__in=Cita.ACTIVAS, inicio__gte=inicio,
                                     inicio__lt=inicio + timedelta(days=1), recordatorio_enviado_en__isnull=True)
    enviados = 0
    for cita in pendientes:
        if avisos.a_cliente(cita.pk, "recordatorio"):
            enviados += 1
        cita.recordatorio_enviado_en = ahora   # se marca aunque no tenga correo, para no reintentar
        cita.save(update_fields=["recordatorio_enviado_en"])
    return enviados
