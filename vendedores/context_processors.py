from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from pedidos.models import CuentaPlataforma

from .models import CarritoCompradorLinea, CarritoLinea


def marketplace(request):
    vendedor = None
    cliente = None
    comprador = None
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        try:
            vendedor = user.vendedor
        except ObjectDoesNotExist:
            vendedor = None
        try:
            cliente = user.cliente_tienda
        except ObjectDoesNotExist:
            cliente = None
        try:
            comprador = user.comprador
        except ObjectDoesNotExist:
            comprador = None
    cuenta = CuentaPlataforma.objects.filter(pk=1).first()
    detalle = cuenta.comision_detalle_pct if cuenta is not None else getattr(settings, "COMISION_PCT", 10)
    mayor = cuenta.comision_mayor_pct if cuenta is not None else getattr(settings, "COMISION_MAYOR_PCT", 5)
    pct = mayor if vendedor is not None and vendedor.tipo in ("mayorista", "importador") else detalle
    pedido_armado = 0
    if cliente is not None:
        pedido_armado = CarritoLinea.objects.filter(carrito__cliente=cliente).count()
    carrito_unidades = 0
    if comprador is not None:
        carrito_unidades = CarritoCompradorLinea.objects.filter(carrito__comprador=comprador).count()
    return {
        "comision_pct": pct,
        "comision_detalle_pct": detalle,
        "comision_mayor_pct": mayor,
        "queda_pct": 100 - int(pct),
        "wompi_pct": getattr(settings, "WOMPI_PCT", "2.65"),
        "wompi_fijo": getattr(settings, "WOMPI_FIJO_COP", 700),
        "wompi_iva": getattr(settings, "WOMPI_IVA_PCT", 19),
        "dias_liquidacion": getattr(settings, "DIAS_LIQUIDACION", 5),
        "vendedor_actual": vendedor,
        "cliente_actual": cliente,
        "cliente_completo": bool(cliente and cliente.registro_completo()),
        "comprador_actual": comprador,
        "pedido_armado": pedido_armado,
        "carrito_unidades": carrito_unidades,
        "visitas_sitio": cuenta.visitas if cuenta is not None else 0,
    }
