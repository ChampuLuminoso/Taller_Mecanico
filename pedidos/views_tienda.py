"""Tienda pública: cualquiera ve precios y stock; para comprar o apartar hay que registrarse."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from cuentas.permisos import tiene_permiso
from inventario import servicios as inventario
from inventario.models import Categoria, Producto

from . import servicios
from .carrito import Carrito
from .forms import CheckoutForm, SolicitudApartadoForm
from .models import Pedido


def _texto_error(e):
    return " ".join(getattr(e, "messages", [str(e)]))


def _cliente(request):
    if request.user.is_authenticated and tiene_permiso(request.user, "tienda.comprar"):
        return getattr(request.user, "cliente", None)
    return None


def _visibles():
    return Producto.objects.filter(activo=True).select_related("categoria", "marca")


# ───────────────────────── Catálogo ─────────────────────────

def catalogo(request):
    q = request.GET.get("q", "").strip()
    categoria = request.GET.get("categoria", "")
    solo_disponibles = request.GET.get("disponibles") == "1"

    productos = _visibles().con_disponibilidad()
    if q:
        for palabra in q.split()[:5]:   # "spark 2015 pastillas" → cada palabra debe aparecer en algún lado
            filtro = (Q(nombre__icontains=palabra) | Q(sku__icontains=palabra) | Q(marca__nombre__icontains=palabra)
                      | Q(compatibilidades__marca_vehiculo__icontains=palabra)
                      | Q(compatibilidades__modelo__icontains=palabra))
            if palabra.isdigit() and len(palabra) == 4:
                anio = int(palabra)
                filtro |= Q(compatibilidades__anio_desde__lte=anio, compatibilidades__anio_hasta__gte=anio)
            productos = productos.filter(filtro)
        productos = productos.distinct()
    if categoria.isdigit():
        productos = productos.filter(categoria_id=categoria)
    if solo_disponibles:
        productos = productos.filter(unidades_disponibles__gt=0)

    pagina = Paginator(productos.order_by("-unidades_disponibles", "nombre"), 24).get_page(request.GET.get("pagina"))
    ctx = {"pagina": pagina, "q": q, "categoria": categoria, "solo_disponibles": solo_disponibles,
           "categorias": Categoria.objects.filter(activo=True)}
    plantilla = "tienda/_resultados.html" if request.headers.get("HX-Request") else "tienda/catalogo.html"
    return render(request, plantilla, ctx)


def producto(request, sku):
    p = get_object_or_404(_visibles(), sku=sku)
    ctx = {"p": p, "compatibilidades": p.compatibilidades.all(),
           "en_carrito": Carrito(request).datos.get(str(p.pk), 0),
           "form_apartado": SolicitudApartadoForm(), "es_cliente": _cliente(request) is not None}
    if request.headers.get("HX-Request"):   # vista rápida dentro de la misma página
        return render(request, "tienda/_vista_rapida.html", ctx)
    return render(request, "tienda/producto.html", ctx)


@require_POST
@login_required
def solicitar_apartado(request, sku):
    p = get_object_or_404(_visibles(), sku=sku)
    cliente = _cliente(request)
    if cliente is None:
        raise PermissionDenied
    form = SolicitudApartadoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa la cantidad.")
    elif form.cleaned_data["cantidad"] > p.disponible:
        messages.error(request, f"Solo hay {p.disponible} disponible(s).")
    else:
        try:
            inventario.solicitar_apartado(cliente, p, form.cleaned_data["cantidad"], form.cleaned_data["nota"],
                                          request.user)
            messages.success(request, "Enviamos tu solicitud de apartado. El taller te contactará para confirmarla.")
        except (ValidationError, PermissionDenied) as e:
            messages.error(request, _texto_error(e))
    return redirect("tienda:producto", sku=sku)


# ───────────────────────── Carrito ─────────────────────────

@require_POST
def carrito_agregar(request, producto_id):
    p = get_object_or_404(_visibles(), pk=producto_id)
    carrito = Carrito(request)
    try:
        pedida = int(request.POST.get("cantidad", 1))
    except ValueError:
        pedida = 1
    actual = carrito.datos.get(str(p.pk), 0)
    if p.disponible <= 0:
        messages.error(request, f"{p.nombre} está agotado.")
    else:
        nueva = carrito.poner(p.pk, min(actual + max(pedida, 1), p.disponible))
        if nueva < actual + pedida:
            messages.info(request, f"De {p.nombre} solo puedes llevar {nueva}.")
        else:
            messages.success(request, f"Agregaste {p.nombre} al carrito.")
    return redirect(request.POST.get("volver") or reverse("tienda:carrito"))


@require_POST
def carrito_cambiar(request, producto_id):
    try:
        cantidad = int(request.POST.get("cantidad", 0))
    except ValueError:
        cantidad = 0
    Carrito(request).poner(producto_id, cantidad)
    return redirect("tienda:carrito")


def carrito(request):
    c = Carrito(request)
    lineas = c.lineas()
    return render(request, "tienda/carrito.html", {
        "lineas": lineas, "subtotal": Carrito.subtotal(lineas),
        "todo_alcanza": all(l.alcanza for l in lineas)})


# ───────────────────────── Comprar ─────────────────────────

def comprar(request):
    if not request.user.is_authenticated:
        messages.info(request, "Para comprar necesitas una cuenta. Tu carrito te espera.")
        return redirect(f"{reverse('cuentas:registro')}?next={reverse('tienda:comprar')}")
    cliente = _cliente(request)
    if cliente is None:
        messages.error(request, "Las compras en la tienda son con una cuenta de cliente.")
        return redirect("tienda:carrito")

    c = Carrito(request)
    lineas = c.lineas()
    if not lineas:
        return redirect("tienda:carrito")
    form = CheckoutForm(request.POST or None, cliente=cliente)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            with transaction.atomic():   # si el pedido falla, tampoco se guarda la dirección nueva
                pedido = servicios.crear_pedido(
                    request.user, cliente, [(l.producto.pk, l.cantidad) for l in lineas],
                    modalidad=d["modalidad"], metodo_pago=d["metodo_pago"], telefono=d["telefono"],
                    direccion=form.direccion_elegida(), nota=d["nota"])
        except (ValidationError, PermissionDenied) as e:
            form.add_error(None, _texto_error(e))
        else:
            c.vaciar()
            messages.success(request, f"¡Pedido #{pedido.pk} recibido! El taller lo confirmará pronto.")
            return redirect("pedidos:mis_pedidos")
    subtotal = Carrito.subtotal(lineas)
    return render(request, "tienda/comprar.html", {"form": form, "lineas": lineas, "subtotal": subtotal})


# ───────────────────────── Mis pedidos (cliente) ─────────────────────────

@login_required
def mis_pedidos(request):
    cliente = _cliente(request)
    if cliente is None:
        raise PermissionDenied
    pedidos = cliente.pedidos.prefetch_related("items").order_by("-creado_en")[:30]
    return render(request, "tienda/mis_pedidos.html", {"pedidos": pedidos})


@require_POST
@login_required
def cancelar_mio(request, pk):
    cliente = _cliente(request)
    pedido = Pedido.objects.filter(pk=pk, cliente=cliente).first() if cliente else None
    if pedido is None:
        raise Http404
    try:
        servicios.cancelar(pedido.pk, request.user)
        messages.success(request, f"Cancelaste el pedido #{pedido.pk}.")
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, _texto_error(e))
    return redirect("pedidos:mis_pedidos")
