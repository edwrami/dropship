from django.db import models

from productos.models import Producto


class Pedido(models.Model):
    ESTADOS = [
        ("pendiente", "Pendiente de pago"),
        ("pagado", "Pagado"),
        ("empacado", "Empacado"),
        ("comprado", "Comprado al proveedor"),
        ("en_casillero", "En casillero"),
        ("enviado", "Enviado"),
        ("entregado", "Entregado"),
        ("fallido", "Fallido"),
    ]
    ESTADOS_PAGO = [
        ("pendiente", "Pendiente"),
        ("reportado", "Cliente reportó el pago"),
        ("aprobado", "Aprobado"),
        ("declinado", "Declinado"),
        ("error", "Error"),
    ]
    ESTADOS_COMISION = [
        ("exenta", "Sin comisión"),
        ("por_confirmar", "Se cobra cuando el cliente pague"),
        ("pendiente", "Pendiente de liquidar"),
        ("reportada", "Comprobante enviado"),
        ("pagada", "Liquidada"),
        ("retenida", "El 10% quedó en ERA shop"),
        ("vencida", "Vencida"),
        ("anulada", "Anulada"),
    ]

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    vendedor = models.ForeignKey(
        "vendedores.Vendedor", null=True, blank=True,
        on_delete=models.PROTECT, related_name="pedidos",
    )
    cliente_tienda = models.ForeignKey(
        "vendedores.ClienteTienda", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="pedidos",
    )
    variante = models.CharField(max_length=200, blank=True)
    cantidad = models.PositiveIntegerField(default=1)

    cliente_nombre = models.CharField(max_length=200)
    cliente_telefono = models.CharField(max_length=50)
    cliente_email = models.EmailField(blank=True)
    cliente_direccion = models.TextField()
    cliente_ciudad = models.CharField(max_length=100)

    clave_contacto = models.CharField(max_length=64, blank=True)
    contacto_responsable = models.CharField(max_length=200, blank=True)
    contacto_telefono = models.CharField(max_length=50, blank=True)
    contacto_whatsapp = models.CharField(max_length=50, blank=True)
    contacto_email = models.EmailField(blank=True)
    contacto_direccion = models.TextField(blank=True)
    contacto_nequi = models.CharField(max_length=20, blank=True)

    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    estado_pago = models.CharField(max_length=20, choices=ESTADOS_PAGO, default="pendiente")
    referencia_pago = models.CharField(max_length=80, unique=True, blank=True)
    wompi_id = models.CharField(max_length=80, blank=True)
    comprobante = models.CharField(max_length=120, blank=True)
    metodo_pago = models.CharField(max_length=40, blank=True)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    comision_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    comision_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tarifa_pasarela_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    neto_vendedor = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    estado_comision = models.CharField(
        max_length=20, choices=ESTADOS_COMISION, default="exenta", db_index=True,
    )
    fecha_limite_comision = models.DateTimeField(null=True, blank=True)
    comprobante_comision = models.CharField(max_length=120, blank=True)
    comprobante_url = models.URLField(max_length=800, blank=True)
    comprobante_ruta = models.CharField(max_length=300, blank=True)
    comision_pagada_en = models.DateTimeField(null=True, blank=True)

    dsers_order_id = models.CharField(max_length=100, blank=True)
    tracking = models.CharField(max_length=200, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)
    notas = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"Pedido #{self.id} - {self.cliente_nombre}"


class MensajePedido(models.Model):
    AUTORES = [
        ("cliente", "Cliente"),
        ("vendedor", "Vendedor"),
        ("plataforma", "ERA shop"),
    ]
    pedido = models.ForeignKey(Pedido, related_name="mensajes", on_delete=models.CASCADE)
    autor = models.CharField(max_length=20, choices=AUTORES)
    nombre = models.CharField(max_length=160)
    texto = models.TextField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado", "id"]

    def __str__(self):
        return f"{self.nombre} en pedido {self.pedido_id}"


class Calificacion(models.Model):
    pedido = models.OneToOneField(Pedido, related_name="calificacion", on_delete=models.CASCADE)
    vendedor = models.ForeignKey(
        "vendedores.Vendedor", related_name="calificaciones", on_delete=models.CASCADE,
    )
    estrellas = models.PositiveSmallIntegerField()
    comentario = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.estrellas} estrellas · pedido {self.pedido_id}"


class Reclamo(models.Model):
    TIPOS = [
        ("reclamo", "Reclamo"),
        ("devolucion", "Devolución"),
    ]
    ESTADOS = [
        ("abierto", "Abierto"),
        ("aceptado", "Aceptado"),
        ("rechazado", "Rechazado"),
        ("cerrado", "Cerrado"),
    ]
    pedido = models.ForeignKey(Pedido, related_name="reclamos", on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    motivo = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default="abierto")
    fecha_limite = models.DateTimeField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.get_tipo_display()} del pedido {self.pedido_id}"


class Pago(models.Model):
    ESTADOS = [
        ("reportado", "Reportado"),
        ("aprobado", "Aprobado"),
        ("declinado", "Declinado"),
        ("error", "Error"),
    ]
    pedido = models.OneToOneField(Pedido, related_name="pago", on_delete=models.CASCADE)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    metodo = models.CharField(max_length=40, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="reportado")
    referencia = models.CharField(max_length=80, blank=True)
    comprobante = models.CharField(max_length=120, blank=True)
    destino_nequi = models.CharField(max_length=20, blank=True)
    wompi_id = models.CharField(max_length=80, blank=True)
    origen = models.CharField(max_length=20, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"Pago del pedido {self.pedido_id}"


class Giro(models.Model):
    ESTADOS = [
        ("pendiente", "Pendiente de giro"),
        ("sin_datos", "Faltan datos del vendedor"),
        ("enviado", "Enviado a Wompi"),
        ("pagado", "Llegó al Nequi del vendedor"),
        ("rechazado", "Rechazado"),
    ]
    pedido = models.OneToOneField(Pedido, related_name="giro", on_delete=models.CASCADE)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    comision_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    destino_nequi = models.CharField(max_length=20, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente")
    payout_id = models.CharField(max_length=80, blank=True)
    detalle = models.CharField(max_length=300, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"Giro del pedido {self.pedido_id}"


class CuentaPlataforma(models.Model):
    titular = models.CharField(max_length=120, blank=True, default="ERA shop")
    nequi = models.CharField(max_length=20, blank=True)
    wompi_publica = models.CharField(max_length=200, blank=True)
    wompi_integridad = models.CharField(max_length=200, blank=True)
    wompi_eventos = models.CharField(max_length=200, blank=True)
    payouts_api_key = models.CharField(max_length=200, blank=True)
    payouts_user_id = models.CharField(max_length=80, blank=True)
    payouts_account_id = models.CharField(max_length=80, blank=True)
    visitas = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "cuenta de comisiones"
        verbose_name_plural = "cuenta de comisiones"

    def __str__(self):
        return self.nequi or "Nequi de ERA shop"
