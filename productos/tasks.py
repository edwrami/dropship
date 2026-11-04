from productos.services.dsers import crear_orden_dsers
from productos.services.sync import sincronizar_catalogo  # noqa: F401


def procesar_pedido(pedido_id):
    from pedidos.models import Pedido
    pedido = Pedido.objects.get(id=pedido_id)
    if pedido.estado_pago != "aprobado":
        pedido.notas = "Esperando pago amarrado al pedido"
        pedido.save(update_fields=["notas"])
        return

    if pedido.es_mayor or pedido.lineas.exists():
        pedido.notas = "Pedido al por mayor. Lo despacha la tienda."
        pedido.save(update_fields=["notas"])
        return

    if pedido.producto.origen != "aliexpress":
        pedido.notas = "Compra manual requerida (outlet)"
        pedido.save()
        return

    if not pedido.producto.dsers_product_id:
        pedido.notas = "Producto sin mapeo a DSers"
        pedido.save()
        return

    direccion = {
        "nombre": pedido.cliente_nombre,
        "telefono": pedido.cliente_telefono,
        "direccion": pedido.cliente_direccion,
        "ciudad": pedido.cliente_ciudad,
    }
    res = crear_orden_dsers(pedido.producto.dsers_product_id, pedido.variante, direccion)
    if "error" in res:
        pedido.notas = res["error"]
        pedido.estado = "fallido"
    else:
        pedido.dsers_order_id = res.get("id", "")
        pedido.estado = "comprado"
    pedido.save()
