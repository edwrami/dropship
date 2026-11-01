from django.conf import settings
from django.db import models

from vendedores.opciones import CONDICIONES, DEPARTAMENTOS_CHOICES, banda_precio


class Producto(models.Model):
    ORIGENES = [
        ("aliexpress", "AliExpress"),
        ("alibaba", "Alibaba"),
        ("outlet", "Outlet marca original"),
        ("vendedor", "Vendedor"),
    ]

    origen = models.CharField(max_length=20, choices=ORIGENES)
    id_externo = models.CharField(max_length=120, unique=True)
    url_origen = models.URLField(max_length=500, blank=True, default="")
    tienda = models.CharField(max_length=100, blank=True)

    titulo = models.CharField(max_length=400)
    descripcion = models.TextField(blank=True)
    imagen = models.URLField(max_length=800, blank=True)
    categoria = models.CharField(max_length=100, blank=True)
    rubro = models.ForeignKey(
        "vendedores.Categoria", null=True, blank=True,
        on_delete=models.PROTECT, related_name="productos",
    )
    vendedor = models.ForeignKey(
        "vendedores.Vendedor", null=True, blank=True,
        on_delete=models.PROTECT, related_name="productos",
    )

    marca = models.CharField(max_length=120, blank=True)
    condicion = models.CharField(max_length=20, choices=CONDICIONES, default="nuevo", db_index=True)
    material = models.CharField(max_length=120, blank=True)
    color = models.CharField(max_length=80, blank=True)
    talla = models.CharField(max_length=40, blank=True)
    sku = models.CharField(max_length=80, blank=True)
    stock = models.PositiveIntegerField(default=1)
    controla_stock = models.BooleanField(default=False)

    ciudad_despacho = models.CharField(max_length=100, blank=True, db_index=True)
    departamento_despacho = models.CharField(
        max_length=60, blank=True, choices=DEPARTAMENTOS_CHOICES, db_index=True,
    )
    tiempo_entrega_min = models.PositiveSmallIntegerField(null=True, blank=True)
    tiempo_entrega_max = models.PositiveSmallIntegerField(null=True, blank=True)
    envio_gratis = models.BooleanField(default=False)
    costo_envio_cop = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    garantia_dias = models.PositiveIntegerField(default=0)
    banda_precio = models.CharField(max_length=20, blank=True, db_index=True)

    precio_costo = models.DecimalField(max_digits=10, decimal_places=2)
    moneda = models.CharField(max_length=5, default="USD")
    peso_libras = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    margen_pct = models.DecimalField(max_digits=5, decimal_places=2, default=settings.MARGEN_DEFAULT)

    precio_venta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_final_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    precio_mayor_cop = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cantidad_minima = models.PositiveIntegerField(default=1)
    unidad_empaque = models.CharField(max_length=80, blank=True)

    dsers_product_id = models.CharField(max_length=120, blank=True)

    activo = models.BooleanField(default=True)
    ultima_sincronizacion = models.DateTimeField(auto_now=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]
        indexes = [
            models.Index(fields=["activo", "precio_final_cop"]),
        ]

    def calcular_precio(self):
        from productos.services.precios import calcular_precio_venta
        return calcular_precio_venta(self)

    def save(self, *args, **kwargs):
        if self.rubro_id:
            self.categoria = self.rubro.nombre
        if self.vendedor_id:
            self.banda_precio = banda_precio(self.precio_final_cop)
            if not self.url_origen:
                self.url_origen = ""
            super().save(*args, **kwargs)
            return
        calc = self.calcular_precio()
        self.precio_venta = calc["precio_venta_usd"]
        self.precio_final_cop = calc["precio_final_cop"]
        self.banda_precio = banda_precio(self.precio_final_cop)
        super().save(*args, **kwargs)

    @property
    def categoria_es(self):
        from productos.categorias_es import traducir_categoria
        if self.rubro_id and getattr(self, "rubro", None) and self.rubro.nombre:
            return self.rubro.nombre
        return traducir_categoria(self.categoria)

    @property
    def entrega_texto(self):
        if self.tiempo_entrega_min and self.tiempo_entrega_max:
            if self.tiempo_entrega_min == self.tiempo_entrega_max:
                return f"{self.tiempo_entrega_min} días"
            return f"{self.tiempo_entrega_min} a {self.tiempo_entrega_max} días"
        if self.tiempo_entrega_max:
            return f"hasta {self.tiempo_entrega_max} días"
        return ""

    def __str__(self):
        return f"[{self.origen}] {self.titulo[:60]}"


class FotoProducto(models.Model):
    producto = models.ForeignKey(Producto, related_name="fotos", on_delete=models.CASCADE)
    url = models.URLField(max_length=800)
    ruta = models.CharField(max_length=300)
    orden = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(fields=["producto", "orden"], name="foto_producto_orden"),
        ]

    def __str__(self):
        return f"Foto {self.orden} de {self.producto_id}"
