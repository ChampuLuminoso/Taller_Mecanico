from django import forms
from django.core.exceptions import ValidationError

from .imagenes import optimizar
from .models import Compatibilidad, Producto


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["sku", "nombre", "categoria", "marca", "proveedor", "precio_venta", "costo",
                  "stock_minimo", "descripcion", "imagen", "activo"]
        labels = {"sku": "ProductoID", "precio_venta": "Precio de venta", "stock_minimo": "Stock mínimo",
                  "marca": "Marca del repuesto", "descripcion": "Descripción"}
        help_texts = {
            "sku": "Código único. Solo mayúsculas, números y guiones (ej. FRE-PAST-001).",
            "stock_minimo": "Cuando lo disponible llegue a este número, se avisa en el panel y por correo.",
            "costo": "Lo que le cuesta al taller. Solo lo ven Subjefe y Jefe.",
        }
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def clean_sku(self):
        return self.cleaned_data["sku"].upper().strip()

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")
        if not imagen or not hasattr(imagen, "content_type"):   # sin cambios
            return imagen
        try:
            return optimizar(imagen, self.cleaned_data.get("sku") or "producto")
        except ValidationError as e:
            raise forms.ValidationError("La imagen " + e.messages[0] + ".")


CompatibilidadFormSet = forms.inlineformset_factory(
    Producto, Compatibilidad, fields=["marca_vehiculo", "modelo", "anio_desde", "anio_hasta"],
    labels={"marca_vehiculo": "Marca del vehículo", "anio_desde": "Año desde", "anio_hasta": "Año hasta"},
    extra=1, can_delete=True,
)


class EdicionRapidaForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["precio_venta", "stock_minimo", "activo"]


class EntradaForm(forms.Form):
    cantidad = forms.IntegerField(min_value=1, max_value=100000)
    motivo = forms.CharField(max_length=255, initial="Compra a proveedor")


class AjusteForm(forms.Form):
    signo = forms.TypedChoiceField(label="Tipo", coerce=int,
                                   choices=[(1, "Sobran unidades (sumar)"), (-1, "Faltan unidades (restar)")])
    cantidad = forms.IntegerField(min_value=1, max_value=100000)
    motivo = forms.CharField(max_length=255, help_text="Ej.: conteo físico del 30 de noviembre.")


class ImportarForm(forms.Form):
    archivo = forms.FileField(label="Archivo de Excel (.xlsx)")

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Sube el archivo en formato .xlsx (la plantilla descargada).")
        if archivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo pesa más de 5 MB.")
        return archivo


# ───────────────────────── Apartados ─────────────────────────

class ResponderSolicitudForm(forms.Form):
    respuesta = forms.CharField(max_length=300, required=False,
                                widget=forms.TextInput(attrs={"placeholder": "Mensaje para el cliente (opcional)"}))
    abono = forms.DecimalField(min_value=0, max_digits=12, decimal_places=0, required=False, initial=0)


class ApartadoDirectoForm(forms.Form):
    sku = forms.CharField(label="ProductoID", max_length=30)
    cliente = forms.CharField(label="Celular o cédula del cliente", max_length=20)
    cantidad = forms.IntegerField(min_value=1, initial=1)
    abono = forms.DecimalField(min_value=0, max_digits=12, decimal_places=0, required=False, initial=0)
    nota = forms.CharField(max_length=300, required=False)


class VariosArchivos(forms.ClearableFileInput):
    allow_multiple_selected = True


class VariosArchivosField(forms.FileField):
    """Campo que acepta varios archivos (patrón de la documentación de Django)."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", VariosArchivos(attrs={"accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        limpiar = super().clean
        if isinstance(data, (list, tuple)):
            if not data and self.required:
                raise forms.ValidationError("Elige al menos una foto.")
            return [limpiar(d, initial) for d in data]
        return [limpiar(data, initial)]


class FotosLoteForm(forms.Form):
    fotos = VariosArchivosField(label="Fotos",
                                help_text="Nombra cada foto con el ProductoID: FRE-PAST-001.jpg. Puedes elegir muchas a la vez.")
