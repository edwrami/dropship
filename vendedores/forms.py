from django import forms
from django.contrib.auth.models import User

from productos.models import Producto

from .models import Categoria
from .opciones import CONDICIONES, DEPARTAMENTOS_CHOICES, RANGOS, TIPOS


def _telefono_valido(valor):
    digitos = "".join(ch for ch in valor if ch.isdigit())
    if len(digitos) < 7:
        raise forms.ValidationError("Escribe un teléfono con al menos 7 dígitos.")
    return valor.strip()


def _nequi_valido(valor):
    digitos = "".join(ch for ch in valor if ch.isdigit())
    if len(digitos) == 12 and digitos.startswith("57"):
        digitos = digitos[2:]
    if len(digitos) != 10 or not digitos.startswith("3"):
        raise forms.ValidationError("El Nequi es un celular colombiano de 10 dígitos, empieza por 3.")
    return digitos


class RegistroForm(forms.Form):
    nombre_tienda = forms.CharField(label="Nombre de la tienda", max_length=160)
    responsable = forms.CharField(label="Responsable", max_length=200)
    documento = forms.CharField(label="Cédula o NIT", max_length=40)
    email = forms.EmailField(label="Correo")
    password = forms.CharField(label="Contraseña", min_length=8, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput)
    telefono = forms.CharField(label="Teléfono", max_length=50)
    whatsapp = forms.CharField(label="WhatsApp", max_length=50)
    nequi = forms.CharField(
        label="Nequi para recibir pagos",
        max_length=20,
        help_text="Celular de 10 dígitos. Aquí llega el 90% de cada venta. ERA shop se queda con el 10%. No se muestra en el catálogo.",
    )
    direccion = forms.CharField(label="Dirección", widget=forms.Textarea(attrs={"rows": 2}))
    ciudad = forms.CharField(label="Ciudad", max_length=100)
    departamento = forms.ChoiceField(label="Departamento", choices=DEPARTAMENTOS_CHOICES)
    tipo = forms.ChoiceField(label="Tipo de vendedor", choices=TIPOS)
    rango_precio = forms.ChoiceField(
        label="Rango de precios de tu mercancía",
        choices=RANGOS,
        help_text="Clasificación inicial. Cuando publiques productos, el programa la ajusta al precio promedio.",
    )
    acepta_terminos = forms.BooleanField(
        label="Acepto la comisión del 10% y que, si no la liquido, mi tienda sale de la página",
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Ese correo ya está registrado.")
        return email

    def clean_nombre_tienda(self):
        nombre = self.cleaned_data["nombre_tienda"].strip()
        from .models import Vendedor
        if Vendedor.objects.filter(nombre_tienda__iexact=nombre).exists():
            raise forms.ValidationError("Ya existe una tienda con ese nombre.")
        return nombre

    def clean_telefono(self):
        return _telefono_valido(self.cleaned_data["telefono"])

    def clean_whatsapp(self):
        return _telefono_valido(self.cleaned_data["whatsapp"])

    def clean_nequi(self):
        return _nequi_valido(self.cleaned_data["nequi"])

    def clean_departamento(self):
        valor = self.cleaned_data["departamento"]
        if not valor:
            raise forms.ValidationError("Elige el departamento.")
        return valor

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password2") and data["password"] != data["password2"]:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return data


class DatosVendedorForm(forms.Form):
    telefono = forms.CharField(label="Teléfono", max_length=50)
    whatsapp = forms.CharField(label="WhatsApp", max_length=50)
    nequi = forms.CharField(
        label="Nequi para recibir el 90%",
        max_length=20,
        help_text="Celular de 10 dígitos. Ahí se gira lo que le corresponde a la tienda.",
    )
    direccion = forms.CharField(label="Dirección", widget=forms.Textarea(attrs={"rows": 2}))
    ciudad = forms.CharField(label="Ciudad", max_length=100)
    departamento = forms.ChoiceField(label="Departamento", choices=DEPARTAMENTOS_CHOICES)
    tipo = forms.ChoiceField(label="Tipo de vendedor", choices=TIPOS)

    def clean_telefono(self):
        return _telefono_valido(self.cleaned_data["telefono"])

    def clean_whatsapp(self):
        return _telefono_valido(self.cleaned_data["whatsapp"])

    def clean_nequi(self):
        return _nequi_valido(self.cleaned_data["nequi"])

    def clean_departamento(self):
        valor = self.cleaned_data["departamento"]
        if not valor:
            raise forms.ValidationError("Elige el departamento.")
        return valor


class ProductoVendedorForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            "titulo", "descripcion", "rubro", "marca", "condicion",
            "material", "color", "talla", "sku", "stock",
            "precio_final_cop", "precio_costo", "precio_mayor_cop",
            "cantidad_minima", "unidad_empaque", "peso_libras",
            "ciudad_despacho", "departamento_despacho",
            "tiempo_entrega_min", "tiempo_entrega_max",
            "envio_gratis", "costo_envio_cop", "garantia_dias",
        ]
        labels = {
            "titulo": "Nombre del producto",
            "descripcion": "Descripción completa",
            "rubro": "Categoría",
            "marca": "Marca",
            "condicion": "Condición",
            "material": "Material",
            "color": "Color",
            "talla": "Talla",
            "sku": "SKU o referencia",
            "stock": "Unidades disponibles",
            "precio_final_cop": "Precio de mostrador (COP)",
            "precio_costo": "Tu costo (privado)",
            "precio_mayor_cop": "Precio al por mayor (COP)",
            "cantidad_minima": "Cantidad mínima al por mayor",
            "unidad_empaque": "Unidad de empaque",
            "peso_libras": "Peso (libras)",
            "ciudad_despacho": "Ciudad de despacho",
            "departamento_despacho": "Departamento de despacho",
            "tiempo_entrega_min": "Entrega mínima (días)",
            "tiempo_entrega_max": "Entrega máxima (días)",
            "envio_gratis": "Envío gratis",
            "costo_envio_cop": "Costo de envío (COP)",
            "garantia_dias": "Garantía (días)",
        }
        help_texts = {
            "descripcion": "Qué es, materiales, medidas, qué incluye y cómo se usa. Mínimo 80 caracteres.",
            "precio_costo": "El cliente no ve este valor.",
            "precio_mayor_cop": "Solo lo ven las tiendas conectadas contigo. El catálogo público sigue mostrando el precio de mostrador.",
            "unidad_empaque": "Por ejemplo: caja x 12, docena, bulto.",
        }
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 6}),
            "condicion": forms.Select(choices=CONDICIONES),
        }

    def __init__(self, *args, mayorista=False, **kwargs):
        self.mayorista = mayorista
        super().__init__(*args, **kwargs)
        if not mayorista:
            for nombre in ("precio_mayor_cop", "cantidad_minima", "unidad_empaque"):
                self.fields.pop(nombre, None)
        else:
            self.fields["precio_mayor_cop"].required = True
            self.fields["cantidad_minima"].required = True
        self.fields["rubro"].queryset = (
            Categoria.objects.filter(padre__isnull=False).select_related("padre").order_by("padre__orden", "orden")
        )
        self.fields["rubro"].label_from_instance = lambda obj: f"{obj.padre.nombre} — {obj.nombre}"
        self.fields["rubro"].empty_label = "Elige la categoría"
        for nombre in ("titulo", "descripcion", "rubro", "stock", "precio_final_cop",
                       "ciudad_despacho", "departamento_despacho",
                       "tiempo_entrega_min", "tiempo_entrega_max"):
            self.fields[nombre].required = True
        self.fields["precio_costo"].required = False
        self.fields["marca"].required = False

    def clean_precio_costo(self):
        valor = self.cleaned_data.get("precio_costo")
        if valor in (None, ""):
            return 0
        return valor

    def clean_descripcion(self):
        texto = (self.cleaned_data.get("descripcion") or "").strip()
        if len(texto) < 80:
            raise forms.ValidationError(
                "Describe el producto con al menos 80 caracteres: qué es, medidas, material y qué incluye."
            )
        return texto

    def clean_precio_final_cop(self):
        precio = self.cleaned_data.get("precio_final_cop") or 0
        if precio <= 0:
            raise forms.ValidationError("Indica el precio de venta en pesos.")
        return precio

    def clean_stock(self):
        stock = self.cleaned_data.get("stock")
        if stock is None or stock < 0:
            raise forms.ValidationError("Indica cuántas unidades tienes.")
        return stock

    def clean(self):
        data = super().clean()
        minimo = data.get("tiempo_entrega_min")
        maximo = data.get("tiempo_entrega_max")
        if minimo is not None and maximo is not None and maximo < minimo:
            self.add_error("tiempo_entrega_max", "El máximo no puede ser menor que el mínimo.")
        if minimo is not None and minimo < 0:
            self.add_error("tiempo_entrega_min", "Los días de entrega no pueden ser negativos.")
        if self.mayorista:
            precio = data.get("precio_mayor_cop")
            minimo_unidades = data.get("cantidad_minima")
            if precio is None or precio <= 0:
                self.add_error("precio_mayor_cop", "Indica el precio al por mayor.")
            if minimo_unidades is None or minimo_unidades < 1:
                self.add_error("cantidad_minima", "La cantidad mínima es al menos 1.")
        return data


class RegistroClienteForm(forms.Form):
    nombre_tienda = forms.CharField(label="Nombre de tu tienda", max_length=160)
    responsable = forms.CharField(label="Responsable", max_length=200)
    documento = forms.CharField(label="Cédula o NIT", max_length=40)
    email = forms.EmailField(label="Correo")
    password = forms.CharField(label="Contraseña", min_length=8, widget=forms.PasswordInput)
    password2 = forms.CharField(label="Repite la contraseña", widget=forms.PasswordInput)
    telefono = forms.CharField(label="Teléfono", max_length=50)
    ciudad = forms.CharField(label="Ciudad", max_length=100)
    departamento = forms.ChoiceField(label="Departamento", choices=DEPARTAMENTOS_CHOICES)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Ese correo ya está registrado.")
        return email

    def clean_telefono(self):
        return _telefono_valido(self.cleaned_data["telefono"])

    def clean_departamento(self):
        valor = self.cleaned_data["departamento"]
        if not valor:
            raise forms.ValidationError("Elige el departamento.")
        return valor

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password2") and data["password"] != data["password2"]:
            self.add_error("password2", "Las contraseñas no coinciden.")
        return data
