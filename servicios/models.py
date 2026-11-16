from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from vendedores.opciones import DEPARTAMENTOS_CHOICES

from .oficios import DIAS, MODOS_COBRO, MODOS_TIEMPO, RUBROS, UNIDADES


class Oferente(models.Model):
    ESTADOS = [
        ("pendiente_pago", "Falta la inscripción"),
        ("pendiente_mensualidad", "Falta la mensualidad para aparecer"),
        ("activo", "Visible en servicios"),
        ("suspendido", "Retirado"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="oferente",
    )
    nombre = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, null=True, blank=True)
    responsable = models.CharField(max_length=200)
    documento = models.CharField(max_length=40)
    telefono = models.CharField(max_length=50)
    whatsapp = models.CharField(max_length=50)
    nequi = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    ciudad = models.CharField(max_length=100, db_index=True)
    departamento = models.CharField(max_length=60, choices=DEPARTAMENTOS_CHOICES, db_index=True)
    rubro = models.CharField(max_length=30, choices=RUBROS, db_index=True)
    oficio = models.CharField(max_length=40, db_index=True)
    descripcion = models.TextField(blank=True)
    precio_cop = models.DecimalField(max_digits=14, decimal_places=2)
    unidad = models.CharField(max_length=20, choices=UNIDADES, default="visita")
    duracion_minutos = models.PositiveSmallIntegerField(default=60)
    disponible_ahora = models.BooleanField(default=True)
    estado = models.CharField(max_length=30, choices=ESTADOS, default="pendiente_pago", db_index=True)
    visitas = models.PositiveIntegerField(default=0)
    foto_url = models.URLField(max_length=800, blank=True)
    foto_ruta = models.CharField(max_length=300, blank=True)
    acepta_terminos = models.BooleanField(default=False)
    mensualidad_hasta = models.DateTimeField(null=True, blank=True, db_index=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ciudad", "nombre"]

    def _slug_unico(self):
        base = (slugify(self.nombre) or "servicio")[:160]
        slug = base
        n = 2
        qs = Oferente.objects.all()
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

    @property
    def inscripcion_pagada(self):
        act = getattr(self, "activacion", None)
        if act is not None and act.estado_pago == "aprobado":
            return True
        return self.estado in ("activo", "pendiente_mensualidad")

    @property
    def mensualidad_al_dia(self):
        return bool(self.mensualidad_hasta and self.mensualidad_hasta >= timezone.now())

    @property
    def visible(self):
        return self.estado == "activo" and self.mensualidad_al_dia

    @property
    def oficio_texto(self):
        from .catalogo import oficio_nombre as nombre_vivo
        return nombre_vivo(self.rubro, self.oficio)

    @property
    def rubro_texto(self):
        from .catalogo import rubro_nombre as nombre_vivo
        return nombre_vivo(self.rubro)

    def __str__(self):
        return self.nombre


class Cobertura(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="coberturas", on_delete=models.CASCADE)
    departamento = models.CharField(max_length=60, choices=DEPARTAMENTOS_CHOICES, db_index=True)
    municipio = models.CharField(max_length=100, db_index=True)
    incluida = models.BooleanField(default=False)
    activa = models.BooleanField(default=False, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["oferente", "departamento", "municipio"],
                name="cobertura_unica",
            ),
        ]

    def __str__(self):
        return f"{self.municipio}, {self.departamento}"


class Especialidad(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="especialidades", on_delete=models.CASCADE)
    rubro = models.CharField(max_length=30, choices=RUBROS, db_index=True)
    oficio = models.CharField(max_length=40, db_index=True)
    precio_cop = models.DecimalField(max_digits=14, decimal_places=2)
    unidad = models.CharField(max_length=20, choices=UNIDADES, default="visita")
    modo_tiempo = models.CharField(max_length=20, choices=MODOS_TIEMPO, default="cita")
    duracion_minutos = models.PositiveSmallIntegerField(default=60)
    modo_cobro = models.CharField(max_length=20, choices=MODOS_COBRO, default="ambos")
    tarifa_detalle = models.TextField(
        blank=True,
        help_text="Lista de precios que ve el cliente. Ejemplo: consulta $80.000 · domicilio $120.000.",
    )
    incluida = models.BooleanField(default=False)
    activa = models.BooleanField(default=False, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["oferente", "rubro", "oficio"], name="especialidad_unica"),
        ]

    @property
    def oficio_texto(self):
        from .catalogo import oficio_nombre as nombre_vivo
        return nombre_vivo(self.rubro, self.oficio)

    @property
    def rubro_texto(self):
        from .catalogo import rubro_nombre as nombre_vivo
        return nombre_vivo(self.rubro)

    def __str__(self):
        return self.oficio_texto


class Bloqueo(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="bloqueos", on_delete=models.CASCADE)
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField()

    class Meta:
        ordering = ["inicio"]


class Horario(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="horarios", on_delete=models.CASCADE)
    dia = models.PositiveSmallIntegerField(choices=DIAS)
    abre = models.TimeField()
    cierra = models.TimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["dia", "abre"]
        constraints = [
            models.UniqueConstraint(fields=["oferente", "dia"], name="horario_oferente_dia"),
        ]

    def __str__(self):
        return f"{self.oferente_id} d{self.dia}"


class FotoTrabajo(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="fotos", on_delete=models.CASCADE)
    url = models.URLField(max_length=800)
    ruta = models.CharField(max_length=300)
    orden = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(fields=["oferente", "orden"], name="foto_trabajo_orden"),
        ]


class PagoActivacion(models.Model):
    oferente = models.OneToOneField(Oferente, related_name="activacion", on_delete=models.CASCADE)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2)
    referencia_pago = models.CharField(max_length=80, unique=True)
    estado_pago = models.CharField(max_length=20, default="pendiente", db_index=True)
    wompi_id = models.CharField(max_length=80, blank=True)
    metodo_pago = models.CharField(max_length=40, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    @property
    def cliente_email(self):
        if self.oferente.email:
            return self.oferente.email
        if self.oferente.user_id:
            return self.oferente.user.email or ""
        return ""

    def __str__(self):
        return self.referencia_pago


class PagoMensualidad(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="pagos_mensuales", on_delete=models.CASCADE)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2)
    referencia_pago = models.CharField(max_length=80, unique=True)
    estado_pago = models.CharField(max_length=20, default="pendiente", db_index=True)
    wompi_id = models.CharField(max_length=80, blank=True)
    metodo_pago = models.CharField(max_length=40, blank=True)
    cubre_hasta = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    @property
    def cliente_email(self):
        if self.oferente.email:
            return self.oferente.email
        if self.oferente.user_id:
            return self.oferente.user.email or ""
        return ""

    def __str__(self):
        return self.referencia_pago


class PagoExtra(models.Model):
    TIPOS = [
        ("ciudad", "Otra ciudad o municipio"),
        ("servicio", "Otro oficio"),
    ]
    oferente = models.ForeignKey(Oferente, related_name="pagos_extra", on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    cobertura = models.ForeignKey(Cobertura, null=True, blank=True, on_delete=models.CASCADE)
    especialidad = models.ForeignKey(Especialidad, null=True, blank=True, on_delete=models.CASCADE)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2)
    referencia_pago = models.CharField(max_length=80, unique=True)
    estado_pago = models.CharField(max_length=20, default="pendiente", db_index=True)
    wompi_id = models.CharField(max_length=80, blank=True)
    metodo_pago = models.CharField(max_length=40, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    @property
    def cliente_email(self):
        if self.oferente.email:
            return self.oferente.email
        if self.oferente.user_id:
            return self.oferente.user.email or ""
        return ""

    def __str__(self):
        return self.referencia_pago


class Cita(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="citas", on_delete=models.PROTECT)
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="citas_servicio",
    )
    especialidad = models.ForeignKey(
        Especialidad, null=True, blank=True, on_delete=models.SET_NULL, related_name="citas",
    )
    cobertura = models.ForeignKey(
        Cobertura, null=True, blank=True, on_delete=models.SET_NULL, related_name="citas",
    )
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField()
    modo_tiempo = models.CharField(max_length=20, choices=MODOS_TIEMPO, default="cita")
    trabajo_realizado = models.BooleanField(default=False, db_index=True)
    realizado_en = models.DateTimeField(null=True, blank=True)
    cliente_nombre = models.CharField(max_length=200)
    cliente_telefono = models.CharField(max_length=50)
    cliente_email = models.EmailField(blank=True)
    nota = models.TextField(blank=True)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2)
    comision_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    comision_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tarifa_pasarela_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    neto_vendedor = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    estado_comision = models.CharField(max_length=20, default="por_confirmar", db_index=True)
    estado_pago = models.CharField(max_length=20, default="pendiente", db_index=True)
    estado = models.CharField(max_length=20, default="pendiente", db_index=True)
    referencia_pago = models.CharField(max_length=80, unique=True, blank=True)
    wompi_id = models.CharField(max_length=80, blank=True)
    metodo_pago = models.CharField(max_length=40, blank=True)
    clave_contacto = models.CharField(max_length=64, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-inicio"]

    @property
    def producto(self):
        class _P:
            precio_final_cop = 0
        return _P()

    def __str__(self):
        return f"Cita #{self.id}"


class PagoCita(models.Model):
    cita = models.OneToOneField(Cita, related_name="pago", on_delete=models.CASCADE)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    metodo = models.CharField(max_length=40, blank=True)
    estado = models.CharField(max_length=20, default="reportado")
    referencia = models.CharField(max_length=80, blank=True)
    wompi_id = models.CharField(max_length=80, blank=True)
    origen = models.CharField(max_length=20, blank=True)
    creado = models.DateTimeField(auto_now_add=True)


class GiroCita(models.Model):
    ESTADOS = [
        ("pendiente", "Pendiente de giro"),
        ("sin_datos", "Faltan datos del oferente"),
        ("enviado", "Enviado a Wompi"),
        ("pagado", "Pagado"),
        ("rechazado", "Rechazado"),
    ]
    cita = models.OneToOneField(Cita, related_name="giro", on_delete=models.CASCADE)
    monto_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    comision_cop = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    destino_nequi = models.CharField(max_length=20, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default="pendiente", db_index=True)
    payout_id = models.CharField(max_length=80, blank=True)
    detalle = models.CharField(max_length=300, blank=True)
    creado = models.DateTimeField(auto_now_add=True)


class Consulta(models.Model):
    oferente = models.ForeignKey(Oferente, related_name="consultas", on_delete=models.CASCADE)
    especialidad = models.ForeignKey(
        Especialidad, null=True, blank=True, on_delete=models.SET_NULL, related_name="consultas",
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="consultas_servicio",
    )
    cliente_nombre = models.CharField(max_length=200)
    cliente_telefono = models.CharField(max_length=50)
    cliente_email = models.EmailField(blank=True)
    clave = models.CharField(max_length=64, db_index=True)
    propuesta_cop = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=20, default="abierta", db_index=True)
    cita = models.ForeignKey(
        "Cita", null=True, blank=True, on_delete=models.SET_NULL, related_name="consultas",
    )
    creado = models.DateTimeField(auto_now_add=True)
    visto_oferente = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado"]


class MensajeConsulta(models.Model):
    consulta = models.ForeignKey(Consulta, related_name="mensajes", on_delete=models.CASCADE)
    autor = models.CharField(max_length=20)
    texto = models.TextField()
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado", "id"]


class Comentario(models.Model):
    cita = models.OneToOneField(Cita, related_name="comentario", on_delete=models.CASCADE)
    oferente = models.ForeignKey(Oferente, related_name="comentarios", on_delete=models.CASCADE)
    estrellas = models.PositiveSmallIntegerField()
    texto = models.TextField(blank=True)
    nombre = models.CharField(max_length=160)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]


class RubroCatalogo(models.Model):
    clave = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class OficioCatalogo(models.Model):
    rubro = models.ForeignKey(RubroCatalogo, related_name="oficios", on_delete=models.CASCADE)
    clave = models.SlugField(max_length=40)
    nombre = models.CharField(max_length=160)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["rubro", "clave"], name="oficio_catalogo_unico"),
        ]

    def __str__(self):
        return self.nombre

