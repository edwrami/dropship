from django import forms
from django.contrib.auth.models import User
from django.utils.dateparse import parse_datetime

from vendedores.forms import _nequi_valido, _telefono_valido
from vendedores.opciones import DEPARTAMENTOS_CHOICES

from .models import Oferente
from .catalogo import oficios_mapa, rubros_choices
from .oficios import MODOS_TIEMPO, UNIDADES


class RegistroOferenteForm(forms.Form):
    nombre = forms.CharField(label="Nombre con el que te buscan", max_length=160)
    responsable = forms.CharField(label="Nombre de quien atiende", max_length=200)
    documento = forms.CharField(label="Cédula o NIT", max_length=40)
    email = forms.EmailField(label="Correo")
    password = forms.CharField(label="Contraseña", min_length=8, widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput, required=False)
    telefono = forms.CharField(label="Teléfono", max_length=50)
    whatsapp = forms.CharField(label="WhatsApp", max_length=50)
    nequi = forms.CharField(
        label="Nequi para recibir lo de cada cita",
        max_length=20,
        help_text="Ahí llega el valor de la cita menos el porcentaje de ERA shop y la tarifa de Wompi.",
    )
    ciudad = forms.CharField(label="Ciudad", max_length=100)
    departamento = forms.ChoiceField(label="Departamento", choices=DEPARTAMENTOS_CHOICES)
    rubro = forms.ChoiceField(label="Tipo de servicio")
    oficio = forms.CharField(label="Oficio", max_length=40)
    descripcion = forms.CharField(
        label="Qué haces",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Cuéntale a la gente el servicio, la zona y cómo trabajas.",
    )
    precio_cop = forms.DecimalField(label="Precio de la cita (COP)", min_value=1000, decimal_places=0)
    unidad = forms.ChoiceField(label="Ese precio es", choices=UNIDADES)
    duracion_minutos = forms.ChoiceField(
        label="Duración de cada cita (si atiendes por horas)",
        choices=[(30, "30 minutos"), (45, "45 minutos"), (60, "1 hora"), (90, "1 hora y media"), (120, "2 horas")],
        initial=60,
    )
    modo_tiempo = forms.ChoiceField(
        label="Cómo agendan este oficio",
        choices=MODOS_TIEMPO,
        initial="cita",
        help_text="Las obras largas se reservan por días o semanas. Barbería y uñas, por cita.",
    )
    acepta_terminos = forms.BooleanField(
        label="Acepto pagar $100.000 de inscripción (incluye el primer mes), $50.000 cada mes siguiente para aparecer, y la comisión de ERA shop en cada cita. Cada ciudad u oficio extra vale otros $100.000",
    )

    def __init__(self, *args, **kwargs):
        self.usuario = kwargs.pop("usuario", None)
        super().__init__(*args, **kwargs)
        self.fields["rubro"].choices = rubros_choices()
        if self.usuario and self.usuario.is_authenticated:
            self.fields["email"].initial = self.usuario.email or self.usuario.username
            self.fields["password"].required = False
            self.fields["password2"].required = False
        else:
            self.fields["password"].required = True
            self.fields["password2"].required = True

    def clean_telefono(self):
        return _telefono_valido(self.cleaned_data["telefono"])

    def clean_whatsapp(self):
        return _telefono_valido(self.cleaned_data["whatsapp"])

    def clean_nequi(self):
        return _nequi_valido(self.cleaned_data["nequi"])

    def clean_oficio(self):
        oficio = (self.cleaned_data.get("oficio") or "").strip()
        rubro = self.data.get("rubro") or self.cleaned_data.get("rubro")
        validos = {clave for clave, _nombre in oficios_mapa().get(rubro) or []}
        if oficio not in validos:
            raise forms.ValidationError("Elige un oficio de esa categoría.")
        return oficio

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if self.usuario and self.usuario.is_authenticated:
            return (self.usuario.email or self.usuario.username).strip().lower()
        return email

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        qs = Oferente.objects.filter(nombre__iexact=nombre)
        if qs.exists():
            raise forms.ValidationError("Ya hay un oferente con ese nombre.")
        return nombre

    def clean(self):
        data = super().clean()
        autenticado = self.usuario and self.usuario.is_authenticated
        email = data.get("email")
        if autenticado:
            return data
        if email and User.objects.filter(username=email).exists():
            if not data.get("password"):
                self.add_error("password", "Escribe la contraseña de esa cuenta para ofrecer oficios con el mismo correo.")
            return data
        if not data.get("password"):
            self.add_error("password", "Escribe una contraseña.")
        elif data.get("password") != data.get("password2"):
            self.add_error("password2", "Las contraseñas no coinciden.")
        return data


class FichaOferenteForm(forms.Form):
    nombre = forms.CharField(label="Nombre público", max_length=160)
    telefono = forms.CharField(label="Teléfono", max_length=50)
    whatsapp = forms.CharField(label="WhatsApp", max_length=50)
    nequi = forms.CharField(label="Nequi", max_length=20)
    ciudad = forms.CharField(label="Ciudad", max_length=100)
    departamento = forms.ChoiceField(label="Departamento", choices=DEPARTAMENTOS_CHOICES)
    rubro = forms.ChoiceField(label="Tipo de servicio")
    oficio = forms.CharField(label="Oficio", max_length=40)
    descripcion = forms.CharField(label="Qué haces", widget=forms.Textarea(attrs={"rows": 4}))
    precio_cop = forms.DecimalField(label="Precio de la cita (COP)", min_value=1000, decimal_places=0)
    unidad = forms.ChoiceField(label="Ese precio es", choices=UNIDADES)
    duracion_minutos = forms.ChoiceField(
        label="Duración de cada cita",
        choices=[(30, "30 minutos"), (45, "45 minutos"), (60, "1 hora"), (90, "1 hora y media"), (120, "2 horas")],
    )
    disponible_ahora = forms.BooleanField(label="Estoy disponible para agendar", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rubro"].choices = rubros_choices()

    def clean_telefono(self):
        return _telefono_valido(self.cleaned_data["telefono"])

    def clean_whatsapp(self):
        return _telefono_valido(self.cleaned_data["whatsapp"])

    def clean_nequi(self):
        return _nequi_valido(self.cleaned_data["nequi"])

    def clean_oficio(self):
        oficio = (self.cleaned_data.get("oficio") or "").strip()
        rubro = self.data.get("rubro") or self.cleaned_data.get("rubro")
        validos = {clave for clave, _nombre in oficios_mapa().get(rubro) or []}
        if oficio not in validos:
            raise forms.ValidationError("Elige un oficio de esa categoría.")
        return oficio


class ContratarForm(forms.Form):
    nombre = forms.CharField(label="Tu nombre", max_length=200)
    telefono = forms.CharField(label="Teléfono", max_length=50)
    email = forms.EmailField(label="Correo", required=False)
    nota = forms.CharField(label="Qué necesitas", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    inicio = forms.CharField(widget=forms.HiddenInput)

    def clean_telefono(self):
        return _telefono_valido(self.cleaned_data["telefono"])

    def clean_inicio(self):
        dt = parse_datetime(self.cleaned_data["inicio"])
        if dt is None:
            raise forms.ValidationError("Elige un espacio libre de la agenda.")
        return dt


class ComentarioForm(forms.Form):
    estrellas = forms.ChoiceField(label="Calificación", choices=[(n, f"{n} de 5") for n in range(5, 0, -1)])
    texto = forms.CharField(label="Comentario", required=False, widget=forms.Textarea(attrs={"rows": 3}))
