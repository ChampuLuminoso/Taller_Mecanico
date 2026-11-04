from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cuentas.auditoria import registrar
from cuentas.decoradores import ip_de, permiso_requerido
from cuentas.permisos import permisos_de

from . import importar as importador
from . import servicios
from .forms import AjusteForm, CompatibilidadFormSet, EdicionRapidaForm, EntradaForm, ImportarForm, ProductoForm
from .models import Categoria, Producto

CAMPOS_AUDITADOS = ["sku", "nombre", "categoria_id", "marca_id", "precio_venta", "costo", "stock_minimo", "activo"]


def _foto(producto):
    return {c: str(getattr(producto, c)) for c in CAMPOS_AUDITADOS}


def _cambios(antes, despues):
    claves = [k for k in antes if antes[k] != despues[k]]
    return {k: antes[k] for k in claves}, {k: despues[k] for k in claves}


# ───────────────────────── Lista ─────────────────────────

FILTROS_ESTADO = {
    "disponibles": Q(activo=True, unidades_disponibles__gt=0),
    "agotados": Q(activo=True, unidades_disponibles__lte=0),
    "bajo": Q(activo=True, unidades_disponibles__lte=F("stock_minimo")),
    "inactivos": Q(activo=False),
}


@permiso_requerido("inventario.ver")
def lista(request):
    q = request.GET.get("q", "").strip()
    categoria = request.GET.get("categoria", "")
    estado = request.GET.get("estado", "")

    productos = Producto.objects.con_disponibilidad().select_related("categoria", "marca")
    if estado in FILTROS_ESTADO:
        productos = productos.filter(FILTROS_ESTADO[estado])
    elif estado != "todos":
        productos = productos.filter(activo=True)
    if q:
        productos = productos.filter(
            Q(sku__icontains=q) | Q(nombre__icontains=q) | Q(marca__nombre__icontains=q)
            | Q(compatibilidades__marca_vehiculo__icontains=q) | Q(compatibilidades__modelo__icontains=q)
        ).distinct()
    if categoria.isdigit():
        productos = productos.filter(categoria_id=categoria)

    pagina = Paginator(productos.order_by("nombre"), 25).get_page(request.GET.get("pagina"))
    contexto = {"pagina": pagina, "q": q, "categoria": categoria, "estado": estado,
                "categorias": Categoria.objects.filter(activo=True), "permisos": permisos_de(request.user)}
    # Con HTMX solo se devuelve la tabla: la página no se recarga mientras escribes.
    plantilla = "inventario/_tabla.html" if request.headers.get("HX-Request") else "inventario/lista.html"
    return render(request, plantilla, contexto)


@permiso_requerido("inventario.editar")
def fila_editar(request, pk):
    """Edición rápida desde la tabla (precio, stock mínimo, activo)."""
    producto = get_object_or_404(Producto.objects.con_disponibilidad(), pk=pk)
    if request.method == "POST":
        antes = _foto(producto)
        form = EdicionRapidaForm(request.POST, instance=producto)
        if form.is_valid():
            producto = form.save()
            a, d = _cambios(antes, _foto(producto))
            if d:
                registrar(request.user, "editar_producto", "Producto", producto.pk, antes=a, despues=d,
                          ip=ip_de(request))
            producto = Producto.objects.con_disponibilidad().get(pk=pk)
            return render(request, "inventario/_fila.html", {"p": producto, "permisos": permisos_de(request.user)})
    else:
        form = EdicionRapidaForm(instance=producto)
    if request.GET.get("cancelar"):
        return render(request, "inventario/_fila.html", {"p": producto, "permisos": permisos_de(request.user)})
    return render(request, "inventario/_fila_edicion.html", {"p": producto, "form": form})


# ───────────────────────── Crear / editar ─────────────────────────

@permiso_requerido("inventario.editar")
def producto_form(request, pk=None):
    producto = get_object_or_404(Producto, pk=pk) if pk else Producto()
    antes = _foto(producto) if pk else None
    form = ProductoForm(request.POST or None, request.FILES or None, instance=producto)
    compat = CompatibilidadFormSet(request.POST or None, instance=producto, prefix="compat")
    if request.method == "POST" and form.is_valid() and compat.is_valid():
        with transaction.atomic():
            producto = form.save()
            compat.instance = producto
            compat.save()
            if pk:
                a, d = _cambios(antes, _foto(producto))
                registrar(request.user, "editar_producto", "Producto", producto.pk, antes=a or None,
                          despues=d or None, ip=ip_de(request))
            else:
                registrar(request.user, "crear_producto", "Producto", producto.pk, despues=_foto(producto),
                          ip=ip_de(request))
        messages.success(request, f"Producto {producto.sku} guardado.")
        if not pk and "inventario.entrada" in permisos_de(request.user):
            messages.info(request, "Ahora registra la cantidad que llegó con «Registrar entrada».")
        return redirect("inventario:detalle", pk=producto.pk)
    return render(request, "inventario/producto_form.html",
                  {"form": form, "compat": compat, "producto": producto if pk else None})


# ───────────────────────── Detalle e historial ─────────────────────────

@permiso_requerido("inventario.ver")
def detalle(request, pk):
    producto = get_object_or_404(Producto.objects.select_related("categoria", "marca", "proveedor"), pk=pk)
    movimientos = Paginator(producto.movimientos.select_related("usuario__empleado"), 30) \
        .get_page(request.GET.get("pagina"))
    return render(request, "inventario/detalle.html", {
        "p": producto,
        "movimientos": movimientos,
        "apartados": producto.apartados.filter(estado="ACTIVO").select_related("cliente"),
        "compatibilidades": producto.compatibilidades.all(),
        "form_entrada": EntradaForm(),
        "form_ajuste": AjusteForm(),
        "permisos": permisos_de(request.user),
    })


def _mover_desde_formulario(request, pk, form_cls, accion):
    form = form_cls(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa la cantidad y el motivo.")
        return redirect("inventario:detalle", pk=pk)
    try:
        accion(form.cleaned_data)
        messages.success(request, "Movimiento registrado.")
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, " ".join(getattr(e, "messages", [str(e)])))
    return redirect("inventario:detalle", pk=pk)


@require_POST
@permiso_requerido("inventario.entrada")
def entrada(request, pk):
    return _mover_desde_formulario(request, pk, EntradaForm, lambda d: servicios.registrar_entrada(
        pk, d["cantidad"], request.user, d["motivo"]))


@require_POST
@permiso_requerido("inventario.ajustar")
def ajuste(request, pk):
    return _mover_desde_formulario(request, pk, AjusteForm, lambda d: servicios.ajustar(
        pk, d["cantidad"], d["signo"], request.user, d["motivo"]))


# ───────────────────────── Excel ─────────────────────────

@permiso_requerido("inventario.importar")
def plantilla(request):
    respuesta = HttpResponse(importador.generar_plantilla(),
                             content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla_productos_taller_francois.xlsx"'
    return respuesta


@permiso_requerido("inventario.importar")
def importar(request):
    form = ImportarForm(request.POST or None, request.FILES or None)
    resultado = None
    if request.method == "POST" and form.is_valid():
        resultado = importador.importar(request.user, form.cleaned_data["archivo"])
        if not resultado.errores:
            registrar(request.user, "importar_productos", "Producto", despues={"creados": resultado.creados},
                      ip=ip_de(request))
            messages.success(request, f"Se cargaron {resultado.creados} productos.")
            return redirect("inventario:lista")
    return render(request, "inventario/importar.html", {"form": form, "resultado": resultado})


# ───────────────────────── Fotos en lote ─────────────────────────

MAX_FOTOS_LOTE = 60


@permiso_requerido("inventario.editar")
def fotos_lote(request):
    """Varias fotos de una vez: el nombre del archivo (sin extensión) es el ProductoID."""
    from pathlib import Path

    from .forms import FotosLoteForm
    from .imagenes import EXTENSIONES, optimizar

    form = FotosLoteForm(request.POST or None, request.FILES or None)
    resultado = None
    if request.method == "POST" and form.is_valid():
        archivos = form.cleaned_data["fotos"][:MAX_FOTOS_LOTE]
        productos = {p.sku: p for p in Producto.objects.filter(
            sku__in=[Path(a.name).stem.upper().strip() for a in archivos])}
        resultado = {"listas": [], "sin_producto": [], "con_error": []}
        for archivo in archivos:
            sku = Path(archivo.name).stem.upper().strip()
            if Path(archivo.name).suffix.lower() not in EXTENSIONES:
                resultado["con_error"].append((archivo.name, "no es una foto (usa JPG, PNG o WebP)"))
                continue
            producto = productos.get(sku)
            if not producto:
                resultado["sin_producto"].append(archivo.name)
                continue
            try:
                contenido = optimizar(archivo, sku)
            except ValidationError as e:
                resultado["con_error"].append((archivo.name, e.messages[0]))
                continue
            if producto.imagen:
                producto.imagen.delete(save=False)   # la foto vieja no se queda ocupando disco
            producto.imagen.save(contenido.name, contenido, save=True)
            resultado["listas"].append(producto)
        if resultado["listas"]:
            registrar(request.user, "fotos_en_lote", "Producto",
                      despues={"productos": [p.sku for p in resultado["listas"]]}, ip=ip_de(request))
        if len(form.cleaned_data["fotos"]) > MAX_FOTOS_LOTE:
            messages.info(request, f"Se procesaron las primeras {MAX_FOTOS_LOTE} fotos. Sube el resto en otra tanda.")
    sin_foto = Producto.objects.filter(activo=True, imagen="").order_by("sku").values_list("sku", "nombre")[:200]
    return render(request, "inventario/fotos_lote.html", {"form": form, "resultado": resultado, "sin_foto": sin_foto})
