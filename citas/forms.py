from django import forms
from django.utils import timezone

from cuentas.models import Vehiculo
from cuentas.validadores import validar_placa

from .models import TipoVisita


class ReservaForm(forms.Form):
    """La fecha y la hora llegan del calendario (botones). El resto lo escribe la persona."""
    tipo = forms.ModelChoiceField(queryset=TipoVisita.objects.filter(activo=True), widget=forms.HiddenInput)
    fecha = forms.DateField(widget=forms.HiddenInput)
    hora = forms.TimeField(error_messages={"required": "Elige una hora del calendario."})

    # Solo para el personal: a quién se le agenda.
    cliente = forms.CharField(label="Celular o cédula del cliente", max_length=20, required=False)

    vehiculo = forms.ModelChoiceField(label="Vehículo", queryset=Vehiculo.objects.none(), required=False,
                                      empty_label="Otro vehículo (escríbelo abajo)")
    placa = forms.CharField(max_length=7, required=False,
                            widget=forms.TextInput(attrs={"autocapitalize": "characters", "placeholder": "ABC123"}))
    marca = forms.CharField(label="Marca del vehículo", max_length=40, required=False)
    modelo = forms.CharField(max_length=60, required=False)
    anio = forms.IntegerField(label="Año", min_value=1950, max_value=timezone.localdate().year + 1, required=False)
    nota = forms.CharField(label="¿Qué le pasa al vehículo?", max_length=800, required=False,
                           widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ej.: chilla al frenar, sobre todo en bajada."}))

    def __init__(self, *args, cliente=None, para_personal=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.para_personal = para_personal
        if cliente:
            self.fields["vehiculo"].queryset = cliente.vehiculos.filter(activo=True)
            if not self.is_bound and self.fields["vehiculo"].queryset.exists():
                self.initial["vehiculo"] = self.fields["vehiculo"].queryset.first().pk
        if not para_personal:
            del self.fields["cliente"]
        if not self.fields["vehiculo"].queryset.exists():
            self.fields["vehiculo"].widget = forms.HiddenInput()

    def clean_placa(self):
        placa = self.cleaned_data["placa"].upper().replace(" ", "").replace("-", "")
        if placa:
            validar_placa(placa)
        return placa

    def clean(self):
        d = super().clean()
        if self.para_personal and not d.get("cliente"):
            self.add_error("cliente", "Escribe el celular o la cédula del cliente.")
        if not d.get("vehiculo"):
            faltan = [n for n in ("placa", "marca", "modelo", "anio") if not d.get(n)]
            if faltan:
                self.add_error(faltan[0], "Elige uno de tus vehículos o escribe placa, marca, modelo y año.")
        return d


class CancelarForm(forms.Form):
    motivo = forms.CharField(max_length=200, required=False,
                             widget=forms.TextInput(attrs={"placeholder": "Motivo (se le envía al cliente)"}))


class BloqueoForm(forms.Form):
    fecha = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    desde = forms.TimeField(label="Desde (opcional)", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    hasta = forms.TimeField(label="Hasta (opcional)", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    motivo = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "Ej.: capacitación, inventario"}))
