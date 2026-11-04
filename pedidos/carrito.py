"""
Carrito guardado en la sesión del navegador: funciona sin registrarse.
Solo guarda {id_producto: cantidad}; precios y stock se leen SIEMPRE de la
base de datos, nunca del navegador (alguien podría manipularlos).
"""
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings

from inventario.models import Producto

CLAVE = "carrito"


@dataclass
class Linea:
    producto: Producto
    cantidad: int

    @property
    def subtotal(self):
        return self.producto.precio_venta * self.cantidad

    @property
    def alcanza(self):
        return self.producto.activo and self.cantidad <= self.producto.disponible


class Carrito:
    def __init__(self, request):
        self.sesion = request.session
        self.datos = {str(k): int(v) for k, v in self.sesion.get(CLAVE, {}).items()}

    def _guardar(self):
        self.sesion[CLAVE] = self.datos
        self.sesion.modified = True

    def poner(self, producto_id, cantidad):
        """Fija la cantidad (0 = quitar). Devuelve la cantidad que quedó."""
        tope = settings.TALLER["MAX_UNIDADES_POR_PRODUCTO"]
        cantidad = max(0, min(int(cantidad), tope))
        if cantidad:
            self.datos[str(producto_id)] = cantidad
        else:
            self.datos.pop(str(producto_id), None)
        self._guardar()
        return cantidad

    def sumar(self, producto_id, cantidad=1):
        return self.poner(producto_id, self.datos.get(str(producto_id), 0) + int(cantidad))

    def vaciar(self):
        self.datos = {}
        self._guardar()

    def __len__(self):
        return sum(self.datos.values())

    def lineas(self):
        productos = Producto.objects.filter(pk__in=self.datos.keys()).select_related("categoria")
        lineas = [Linea(p, self.datos[str(p.pk)]) for p in productos]
        # Si un producto se borró o desactivó, sale del carrito sin hacer ruido.
        vigentes = {str(l.producto.pk) for l in lineas}
        if set(self.datos) - vigentes:
            self.datos = {k: v for k, v in self.datos.items() if k in vigentes}
            self._guardar()
        return sorted(lineas, key=lambda l: l.producto.nombre)

    @staticmethod
    def subtotal(lineas):
        return sum((l.subtotal for l in lineas), Decimal(0))
