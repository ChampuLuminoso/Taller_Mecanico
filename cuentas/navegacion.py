"""
Secciones del encabezado según quién entra. El ORDEN de esta lista es también el
orden del deslizamiento: deslizar a la izquierda va a la siguiente sección y a la
derecha a la anterior (igual que las pestañas de una app).
"""
from django.conf import settings
from django.urls import reverse

from cuentas.permisos import permisos_de
from pedidos.carrito import Carrito


def _secciones(request):
    u = request.user
    if not u.is_authenticated:
        return [("Tienda", "tienda:catalogo"), ("Agendar cita", "citas:agendar"),
                ("Carrito", "tienda:carrito"), ("Entrar", "cuentas:login")]
    p = permisos_de(u)
    if "inventario.ver" in p:          # personal del taller: primero su trabajo, al final la tienda
        s = [("Panel", "cuentas:panel"), ("Inventario", "inventario:lista"),
             ("Pedidos", "pedidos:lista"), ("Agenda", "citas:agenda")]
        s.append(("Apartados", "apartados:solicitudes" if "apartados.aprobar" in p else "apartados:lista"))
        if "reportes.ver" in p:
            s.append(("Ventas", "reportes:ventas"))
        if "clientes.ver_historial" in p:
            s.append(("Clientes", "reportes:clientes"))
        if "personal.ver" in p:
            s.append(("Personal", "cuentas:personal"))
        s.append(("Tienda", "tienda:catalogo"))
        return s
    if "sistema.mantenimiento" in p:
        return [("Panel", "cuentas:panel"), ("Mantenimiento", "admin:index"), ("Tienda", "tienda:catalogo")]
    # Cliente
    return [("Tienda", "tienda:catalogo"), ("Mis citas", "citas:mis_citas"), ("Mis pedidos", "pedidos:mis_pedidos"),
            ("Carrito", "tienda:carrito"), ("Mi cuenta", "cuentas:panel")]


def _prefijos(url):
    """Qué rutas cuentan como 'dentro' de cada sección (para marcarla activa)."""
    if url == "/":
        return ["/tienda/"]
    if url.startswith("/panel/apartados/"):
        return ["/panel/apartados/"]
    if url.startswith("/citas/agendar/"):
        return ["/citas/"]
    return [url]


def contexto(request):
    secciones, activa = [], None
    for i, (nombre, ruta) in enumerate(_secciones(request)):
        url = reverse(ruta)
        secciones.append({"nombre": nombre, "url": url, "orden": i})
        coincide = request.path == url or any(request.path.startswith(pre) for pre in _prefijos(url))
        # La coincidencia más larga gana: /panel/inventario/3/ es Inventario, no Panel.
        if coincide and (activa is None or len(url) > len(secciones[activa]["url"])):
            activa = i
    for s in secciones:
        s["activa"] = s["orden"] == activa
        if s["url"] == reverse("tienda:carrito"):
            s["insignia"] = len(Carrito(request)) or ""
    return {"menu_secciones": secciones, "seccion_activa": activa if activa is not None else -1,
            "marca": settings.MARCA}
