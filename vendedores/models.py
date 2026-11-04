from django.conf import settings
from django.db import models
from django.utils.text import slugify

from .opciones import DEPARTAMENTOS_CHOICES, RANGOS, TIPOS


class Categoria(models.Model):
    nombre = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160, unique=True)
    padre = models.ForeignKey(
        "self", null=True, blank=True, related_name="hijos", on_delete=models.CASCADE,
    )
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "categoría"
        verbose_name_plural = "categorías"

    def __str__(self):
        if self.padre_id:
            return f"{self.padre.nombre} — {self.nombre}"
        return self.nombre


class Vendedor(models.Model):
    ESTADOS = [
        ("activo", "Activo en la página"),
        ("expulsado", "Retirado de la página"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendedor",
    )
    nombre_tienda = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=180, unique=True, null=True, blank=True)
    responsable = models.CharField(max_length=200)
    documento = models.CharField(max_length=40, help_text="Cédula o NIT. No se muestra al público.")
    telefono = models.CharField(max_length=50)
    whatsapp = models.CharField(max_length=50)
    nequi = models.CharField(max_length=20, blank=True, help_text="Número Nequi que recibe el pago del cliente.")
    direccion = models.TextField(help_text="Se muestra al cliente solo después del pedido.")
    ciudad = models.CharField(max_length=100, db_index=True)
    departamento = models.CharField(max_length=60, choices=DEPARTAMENTOS_CHOICES, db_index=True)
    tipo = models.CharField(max_length=20, choices=TIPOS, db_index=True)
    rango_precio = models.CharField(max_length=20, choices=RANGOS, db_index=True)
    precio_desde = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    precio_hasta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    categorias = models.ManyToManyField(Categoria, related_name="vendedores", blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="activo", db_index=True)
    motivo_sancion = models.TextField(blank=True)
    fecha_sancion = models.DateTimeField(null=True, blank=True)
    acepta_terminos = models.BooleanField(default=False)
    visitas = models.PositiveIntegerField(default=0)
    calificacion_manual = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True,
        help_text="Si tiene valor, esta es la calificación que ve el público. Vacío usa el promedio de los comentarios.",
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ciudad", "tipo", "nombre_tienda"]
        verbose_name = "vendedor"
        verbose_name_plural = "vendedores"

    def _slug_unico(self):
        base = (slugify(self.nombre_tienda) or "tienda")[:160]
        slug = base
        n = 2
        qs = Vendedor.objects.all()
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        while qs.filter(slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._slug_unico()
            campos = kwargs.get("update_fields")
            if campos is not None:
                kwargs["update_fields"] = set(campos) | {"slug"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre_tienda} · {self.ciudad} · {self.get_tipo_display()}"

    @property
    def es_proveedor(self):
        return self.estado == "activo" and self.tipo in ("mayorista", "importador")


class ClienteTienda(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cliente_tienda",
    )
    nombre_tienda = models.CharField(max_length=160)
    responsable = models.CharField(max_length=200)
    documento = models.CharField(max_length=40)
    telefono = models.CharField(max_length=50)
    direccion = models.TextField(blank=True)
    barrio = models.CharField(max_length=120, blank=True)
    ciudad = models.CharField(max_length=100, db_index=True)
    departamento = models.CharField(max_length=60, choices=DEPARTAMENTOS_CHOICES, db_index=True)
    referencia = models.CharField(max_length=200, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ciudad", "nombre_tienda"]
        verbose_name = "tienda compradora"
        verbose_name_plural = "tiendas compradoras"

    def registro_completo(self):
        documento = "".join(ch for ch in (self.documento or "") if ch.isdigit())
        return bool(
            (self.nombre_tienda or "").strip()
            and (self.responsable or "").strip()
            and len(documento) >= 5
            and (self.telefono or "").strip()
            and (self.direccion or "").strip()
            and (self.ciudad or "").strip()
            and (self.departamento or "").strip()
        )

    def __str__(self):
        return f"{self.nombre_tienda} · {self.ciudad}"


class Comprador(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comprador",
    )
    nombre = models.CharField(max_length=200)
    documento = models.CharField(max_length=40)
    telefono = models.CharField(max_length=50)
    direccion = models.TextField()
    barrio = models.CharField(max_length=120, blank=True)
    ciudad = models.CharField(max_length=100)
    departamento = models.CharField(max_length=60, choices=DEPARTAMENTOS_CHOICES)
    referencia = models.CharField(max_length=200, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "comprador"
        verbose_name_plural = "compradores"

    def __str__(self):
        return f"{self.nombre} · {self.ciudad}"


class Conexion(models.Model):
    cliente = models.ForeignKey(ClienteTienda, related_name="conexiones", on_delete=models.CASCADE)
    proveedor = models.ForeignKey(Vendedor, related_name="clientes_conectados", on_delete=models.CASCADE)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cliente", "proveedor"], name="conexion_cliente_proveedor"),
        ]
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.cliente.nombre_tienda} → {self.proveedor.nombre_tienda}"


class Carrito(models.Model):
    cliente = models.ForeignKey(ClienteTienda, related_name="carritos", on_delete=models.CASCADE)
    proveedor = models.ForeignKey(Vendedor, related_name="carritos", on_delete=models.CASCADE)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cliente", "proveedor"], name="carrito_cliente_proveedor"),
        ]

    def __str__(self):
        return f"Pedido de {self.cliente.nombre_tienda} con {self.proveedor.nombre_tienda}"


class CarritoLinea(models.Model):
    carrito = models.ForeignKey(Carrito, related_name="lineas", on_delete=models.CASCADE)
    producto = models.ForeignKey("productos.Producto", on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["carrito", "producto"], name="carrito_linea_producto"),
        ]

    def __str__(self):
        return f"{self.producto_id} × {self.cantidad}"
