from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from vendedores.services import activar_cobro_comision

from .models import Calificacion, CuentaPlataforma, MensajePedido, Pedido, Reclamo


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "producto", "vendedor", "cliente_nombre", "estado_pago", "estado",
        "monto_cop", "comision_cop", "estado_comision", "referencia_pago",
        "metodo_pago", "comprobante", "creado",
    )
    list_filter = ("estado", "estado_pago", "estado_comision")
    search_fields = (
        "cliente_nombre", "cliente_telefono", "referencia_pago",
        "comprobante", "comprobante_comision", "wompi_id", "tracking",
        "vendedor__nombre_tienda",
    )
    actions = ("marcar_pagado", "confirmar_comision", "rechazar_comision")

    @admin.action(description="Confirmar pago directo y comprar al proveedor")
    def marcar_pagado(self, request, queryset):
        from productos.tasks import procesar_pedido

        for pedido in queryset.exclude(estado_pago="aprobado"):
            pedido.estado_pago = "aprobado"
            if pedido.estado == "pendiente":
                pedido.estado = "pagado"
            pedido.save()
            activar_cobro_comision(pedido)
            try:
                procesar_pedido(pedido.id)
            except Exception as e:
                pedido.notas = f"Pagado. Error al comprar al proveedor: {e}"
                pedido.save(update_fields=["notas"])

    @admin.action(description="Confirmar que la comisión del 10% fue pagada")
    def confirmar_comision(self, request, queryset):
        ahora = timezone.now()
        queryset.filter(estado_comision__in=["pendiente", "reportada"]).update(
            estado_comision="pagada",
            comision_pagada_en=ahora,
        )

    @admin.action(description="Rechazar comprobante de comisión y dar 2 días")
    def rechazar_comision(self, request, queryset):
        limite = timezone.now() + timedelta(days=2)
        queryset.filter(estado_comision="reportada").update(
            estado_comision="pendiente",
            fecha_limite_comision=limite,
            comprobante_comision="",
            comprobante_url="",
            comprobante_ruta="",
        )


@admin.register(MensajePedido)
class MensajePedidoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "autor", "nombre", "creado")
    search_fields = ("texto", "nombre", "pedido__cliente_nombre")


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ("pedido", "vendedor", "estrellas", "creado")
    search_fields = ("comentario", "vendedor__nombre_tienda")


@admin.register(Reclamo)
class ReclamoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "tipo", "estado", "fecha_limite", "creado")
    list_filter = ("tipo", "estado")


@admin.register(CuentaPlataforma)
class CuentaPlataformaAdmin(admin.ModelAdmin):
    list_display = ("titular", "nequi", "wompi_publica")
    exclude = ("wompi_integridad", "wompi_eventos")
