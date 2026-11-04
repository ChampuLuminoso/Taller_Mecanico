from django import forms

from cuentas.models import Direccion
from cuentas.validadores import validar_telefono_co

from .models import Pedido


class CheckoutForm(forms.Form):
    modalidad = forms.ChoiceField(label="¿Cómo lo quieres recibir?", choices=Pedido.MODALIDADES,
                                  widget=forms.RadioSelect, initial=Pedido.ENVIO)
    direccion = forms.ModelChoiceField(label="Dirección de entrega", queryset=Direccion.objects.none(),
                                       required=False, empty_label="Nueva dirección (escríbela abajo)")
    localidad = forms.ChoiceField(choices=[("", "Elige la localidad")] + Direccion.LOCALIDADES, required=False)
    barrio = forms.CharField(max_length=80, required=False)
    direccion_texto = forms.CharField(label="Dirección", max_length=150, required=False,
                                      widget=forms.TextInput(attrs={"placeholder": "Ej.: Calle 45 # 12-30, apto 301"}))
    indicaciones = forms.CharField(max_length=200, required=False,
                                   widget=forms.TextInput(attrs={"placeholder": "Ej.: casa esquinera, portón azul"}))
    metodo_pago = forms.ChoiceField(label="Pago", choices=Pedido.METODOS_PAGO, widget=forms.RadioSelect,
                                    initial=Pedido.CONTRA_ENTREGA)
    telefono = forms.CharField(label="Celular de contacto", max_length=20, validators=[validar_telefono_co])
    nota = forms.CharField(label="Nota para el taller (opcional)", max_length=500, required=False,
                           widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, cliente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cliente = cliente
        qs = cliente.direcciones.all() if cliente else Direccion.objects.none()
        self.fields["direccion"].queryset = qs
        if not self.is_bound:
            self.initial.setdefault("telefono", cliente.telefono if cliente else "")
            principal = qs.filter(principal=True).first() or qs.first()
            if principal:
                self.initial["direccion"] = principal.pk
        if not qs.exists():
            self.fields["direccion"].widget = forms.HiddenInput()

    def clean(self):
        d = super().clean()
        if d.get("modalidad") == Pedido.ENVIO:
            d["metodo_pago"] = Pedido.CONTRA_ENTREGA    # a domicilio siempre se paga al recibir
            if not d.get("direccion"):
                for campo in ("localidad", "barrio", "direccion_texto"):
                    if not d.get(campo):
                        self.add_error(campo, "Necesitamos este dato para llevarte el pedido.")
        return d

    def direccion_elegida(self):
        """Devuelve la dirección guardada o crea la nueva (se reutiliza en próximas compras)."""
        d = self.cleaned_data
        if d["modalidad"] != Pedido.ENVIO:
            return None
        if d.get("direccion"):
            return d["direccion"]
        return Direccion.objects.create(
            cliente=self.cliente, localidad=d["localidad"], barrio=d["barrio"].strip(),
            direccion=d["direccion_texto"].strip(), indicaciones=d["indicaciones"].strip(),
            principal=not self.cliente.direcciones.exists())


class SolicitudApartadoForm(forms.Form):
    cantidad = forms.IntegerField(min_value=1, max_value=20, initial=1)
    nota = forms.CharField(label="Nota para el taller", max_length=500, required=False,
                           widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ej.: lo recojo el sábado en la mañana"}))
