import logging

from productos.models import Producto

log = logging.getLogger("dropship.sync")


def _en_uso(producto):
    from pedidos.models import LineaPedido, Pedido
    from vendedores.models import CarritoCompradorLinea, CarritoLinea

    if Pedido.objects.filter(producto=producto).exists():
        return True
    if LineaPedido.objects.filter(producto=producto).exists():
        return True
    if CarritoLinea.objects.filter(producto=producto).exists():
        return True
    return CarritoCompradorLinea.objects.filter(producto=producto).exists()


def _eliminar_o_ocultar(producto):
    if _en_uso(producto):
        producto.activo = False
        producto.save(update_fields=["activo"])
        return "ocultado"
    producto.delete()
    return "eliminado"


def sincronizar_catalogo():
    """Quita el catálogo de relleno. Solo quedan los productos de quien vende."""
    eliminados = 0
    for producto in Producto.objects.filter(vendedor__isnull=True).exclude(origen="vendedor"):
        _eliminar_o_ocultar(producto)
        eliminados += 1
    resultado = {"nuevos": 0, "actualizados": 0, "eliminados": eliminados}
    log.info("Sincronización: %s", resultado)
    return resultado
