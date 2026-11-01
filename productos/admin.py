from django.contrib import admin
from .models import FotoProducto, Producto


class FotoInline(admin.TabularInline):
    model = FotoProducto
    extra = 0
    readonly_fields = ("url", "ruta")


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    inlines = [FotoInline]
    list_display = (
        "titulo", "origen", "vendedor", "rubro", "ciudad_despacho",
        "banda_precio", "precio_final_cop", "tiempo_entrega_max", "activo",
    )
    list_filter = (
        "origen", "activo", "condicion", "banda_precio", "departamento_despacho",
        "envio_gratis", "ciudad_despacho",
    )
    search_fields = ("titulo", "id_externo", "marca", "sku", "ciudad_despacho", "descripcion")
    readonly_fields = ("precio_venta", "precio_final_cop", "ultima_sincronizacion")
