from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

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
        help_text="Celular de 10 dígitos. Ahí llega lo que queda después del 10% y de la tarifa de Wompi. No se muestra en el catálogo.",
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
        label="Acepto que de cada venta se descuentan el 10% de ERA shop y la tarifa de Wompi, y que yo recibo el resto en mi Nequi",
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
        label="Nequi para recibir el restante",
        max_length=20,
        help_text="Celular de 10 dígitos. Ahí llega el precio menos el 10% y menos la tarifa de Wompi.",
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
            "precio_final_cop", "precio_promo_cop", "promo_hasta", "precio_costo", "precio_mayor_cop",
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
            "precio_final_cop": "Precio normal (COP)",
            "precio_promo_cop": "Precio en promoción (COP)",
            "promo_hasta": "La promoción termina",
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
            "stock": "Déjalo vacío para publicar sin límite de unidades.",
            "precio_final_cop": "Puede ir ya con el 10% y la tarifa de Wompi incluidos.",
            "precio_promo_cop": "Opcional. Menor que el precio normal. El cliente paga este valor mientras la promoción esté vigente. El 10% y Wompi se calculan sobre él.",
            "promo_hasta": "Opcional. Si la dejas vacía, la promoción sigue hasta que la quites.",
            "precio_costo": "El cliente no ve este valor. Sirve para avisarte si el precio te deja pérdida.",
            "precio_mayor_cop": "Solo lo ven las tiendas conectadas contigo. El catálogo público sigue mostrando el precio de mostrador.",
            "unidad_empaque": "Por ejemplo: caja x 12, docena, bulto.",
        }
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 6}),
            "condicion": forms.Select(choices=CONDICIONES),
            "promo_hasta": forms.DateInput(attrs={"type": "date"}),
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
        for nombre in ("titulo", "descripcion", "rubro", "precio_final_cop",
                       "ciudad_despacho", "departamento_despacho",
                       "tiempo_entrega_min", "tiempo_entrega_max"):
            self.fields[nombre].required = True
        self.fields["stock"].required = False
        self.fields["precio_promo_cop"].required = False
        self.fields["promo_hasta"].required = False
        self.fields["promo_hasta"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["promo_hasta"].widget.format = "%Y-%m-%d"
        if self.instance.pk and not self.instance.controla_stock:
            self.initial["stock"] = None
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
        if stock is None:
            return None
        if stock < 0:
            raise forms.ValidationError("Las unidades no pueden ser negativas.")
        return stock

    def clean(self):
        data = super().clean()
        promo = data.get("precio_promo_cop")
        precio = data.get("precio_final_cop")
        hasta = data.get("promo_hasta")
        if promo is not None:
            if promo <= 0:
                self.add_error("precio_promo_cop", "El precio en promoción debe ser mayor que cero.")
            elif precio and promo >= precio:
                self.add_error("precio_promo_cop", "La promoción tiene que ser menor que el precio normal.")
        elif hasta:
            self.add_error("precio_promo_cop", "Escribe el precio en promoción o quita la fecha.")
        if hasta and hasta < timezone.localdate():
            self.add_error("promo_hasta", "Esa fecha ya pasó.")
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

    def save(self, commit=True):
        stock_anterior = self.instance.stock if self.instance.pk else 0
        producto = super().save(commit=False)
        stock = self.cleaned_data.get("stock")
        if stock is None:
            producto.controla_stock = False
            producto.stock = stock_anterior or 0
        else:
            producto.controla_stock = True
            producto.stock = stock
        if commit:
            producto.save()
            self.save_m2m()
        return producto


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
