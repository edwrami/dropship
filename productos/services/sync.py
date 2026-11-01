import logging

from productos.models import Producto
from productos.services.aliexpress import extraer_producto_aliexpress
from productos.services.catalogo_auto import cargar_productos_nuevos
from productos.services.outlets import extraer_producto_outlet

log = logging.getLogger("dropship.sync")


def _extraer(producto):
    if producto.origen == "aliexpress" or "aliexpress." in (producto.url_origen or ""):
        return extraer_producto_aliexpress(producto.url_origen)
    return extraer_producto_outlet(producto.url_origen)


def _ya_no_existe(datos):
    titulo = (datos.get("titulo") or "").lower()
    if any(x in titulo for x in ("not found", "no encontrado", "unavailable", "no longer")):
        return True
    if float(datos.get("precio_costo") or 0) <= 0 and not datos.get("imagen"):
        msg = str(datos.get("error") or "").lower()
        return any(x in msg for x in ("404", "not found", "no encontrado"))
    return False


def _eliminar_o_ocultar(producto):
    from pedidos.models import Pedido

    if Pedido.objects.filter(producto=producto).exists():
        producto.activo = False
        producto.save(update_fields=["activo"])
        return "ocultado"
    producto.delete()
    return "eliminado"


def sincronizar_catalogo():
    """Publica productos nuevos, actualiza los vigentes y quita los que ya no existen."""
    ids_previos = set(Producto.objects.values_list("id", flat=True))
    nuevos = cargar_productos_nuevos()
    actualizados = 0
    eliminados = 0
    for producto in Producto.objects.filter(pk__in=ids_previos):
        if producto.vendedor_id or producto.origen == "vendedor":
            continue
        if (producto.id_externo or "").startswith("mayorista-"):
            continue
        try:
            datos = _extraer(producto)
        except Exception as e:
            log.warning("Fallo al extraer %s: %s", producto.id, e)
            continue
        if "error" in datos:
            log.warning("Sin ficha actualizada %s: %s", producto.id, datos.get("error"))
            continue
        if _ya_no_existe(datos):
            _eliminar_o_ocultar(producto)
            eliminados += 1
            continue
        titulo = (datos.get("titulo") or "").strip()
        if titulo and titulo.lower() not in ("sin título", "sin titulo"):
            producto.titulo = titulo
        producto.imagen = datos.get("imagen") or producto.imagen or ""
        producto.moneda = datos.get("moneda") or producto.moneda
        costo = datos.get("precio_costo")
        if costo:
            producto.precio_costo = costo
        producto.activo = True
        producto.save()
        actualizados += 1
    resultado = {"nuevos": nuevos, "actualizados": actualizados, "eliminados": eliminados}
    log.info("Sincronización: %s", resultado)
    return resultado
