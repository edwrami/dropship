from django.contrib import admin

from .models import Categoria, ClienteTienda, Conexion, Vendedor
from .services import expulsar_vendedor


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "padre", "orden", "slug")
    list_filter = ("padre",)
    search_fields = ("nombre", "slug")


@admin.register(Vendedor)
class VendedorAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_tienda", "ciudad", "departamento", "tipo", "rango_precio",
        "precio_desde", "precio_hasta", "estado", "creado",
    )
    list_filter = ("estado", "departamento", "ciudad", "tipo", "rango_precio")
    search_fields = ("nombre_tienda", "responsable", "ciudad", "documento", "user__email")
    filter_horizontal = ("categorias",)
    actions = ("retirar", "reactivar")

    @admin.action(description="Retirar de la página")
    def retirar(self, request, queryset):
        for vendedor in queryset:
            expulsar_vendedor(vendedor, "Retiro manual desde el administrador.")

    @admin.action(description="Reactivar tienda (solo si ya liquidó)")
    def reactivar(self, request, queryset):
        from productos.models import Producto

        for vendedor in queryset.filter(estado="expulsado"):
            vendedor.estado = "activo"
            vendedor.motivo_sancion = ""
            vendedor.fecha_sancion = None
            vendedor.save(update_fields=["estado", "motivo_sancion", "fecha_sancion"])
            Producto.objects.filter(vendedor=vendedor).update(activo=True)


@admin.register(ClienteTienda)
class ClienteTiendaAdmin(admin.ModelAdmin):
    list_display = ("nombre_tienda", "ciudad", "departamento", "responsable", "creado")
    search_fields = ("nombre_tienda", "ciudad", "responsable", "user__email")


@admin.register(Conexion)
class ConexionAdmin(admin.ModelAdmin):
    list_display = ("cliente", "proveedor", "creado")
    search_fields = ("cliente__nombre_tienda", "proveedor__nombre_tienda")
