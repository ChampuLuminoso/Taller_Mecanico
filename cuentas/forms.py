from django import forms
from django.contrib.auth import password_validation

from .validadores import validar_mayor_de_edad, validar_telefono_co


class ConfirmarClaveMixin(forms.Form):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="Mínimo 10 caracteres. Evita contraseñas comunes o solo números.")
    password2 = forms.CharField(label="Repite la contraseña",
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get("password1"), datos.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        elif p1:
            try:
                password_validation.validate_password(p1)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return datos


class RegistroClienteForm(ConfirmarClaveMixin):
    nombres = forms.CharField(max_length=80)
    apellidos = forms.CharField(max_length=80)
    email = forms.EmailField(label="Correo", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    telefono = forms.CharField(label="Celular", max_length=20, validators=[validar_telefono_co],
                               widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}))
    fecha_nacimiento = forms.DateField(label="Fecha de nacimiento", validators=[validar_mayor_de_edad],
                                       widget=forms.DateInput(attrs={"type": "date"}))
    acepta_politica = forms.BooleanField(
        label="Autorizo el tratamiento de mis datos personales según la política de privacidad.",
        required=True,
        error_messages={"required": "Para crear la cuenta debes aceptar la política de tratamiento de datos."},
    )
    acepta_marketing = forms.BooleanField(label="Quiero recibir promociones (opcional).", required=False)

    field_order = ["nombres", "apellidos", "email", "telefono", "fecha_nacimiento",
                   "password1", "password2", "acepta_politica", "acepta_marketing"]


class PersonalForm(ConfirmarClaveMixin):
    rol = forms.ChoiceField(choices=[])
    nombres = forms.CharField(max_length=80)
    apellidos = forms.CharField(max_length=80)
    numero_documento = forms.CharField(label="Cédula", max_length=20)
    email = forms.EmailField(label="Correo")
    telefono = forms.CharField(label="Celular", max_length=20, validators=[validar_telefono_co])
    cargo = forms.CharField(max_length=60)
    hace_domicilios = forms.BooleanField(label="Hace domicilios", required=False)

    field_order = ["rol", "nombres", "apellidos", "numero_documento", "email", "telefono",
                   "cargo", "hace_domicilios", "password1", "password2"]

    def __init__(self, *args, roles_permitidos=(), **kwargs):
        super().__init__(*args, **kwargs)
        nombres = {"EMPLEADO": "Empleado", "SUBJEFE": "Subjefe", "JEFE": "Jefe"}
        self.fields["rol"].choices = [(r, nombres[r]) for r in roles_permitidos]


class BloqueoForm(forms.Form):
    motivo = forms.CharField(max_length=255, widget=forms.TextInput(attrs={"placeholder": "Motivo del bloqueo"}))
