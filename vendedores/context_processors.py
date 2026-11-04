from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from pedidos.models import CuentaPlataforma


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
    return {
        "comision_pct": getattr(settings, "COMISION_PCT", 10),
        "queda_pct": 100 - int(getattr(settings, "COMISION_PCT", 10)),
        "wompi_pct": getattr(settings, "WOMPI_PCT", "2.65"),
        "wompi_fijo": getattr(settings, "WOMPI_FIJO_COP", 700),
        "wompi_iva": getattr(settings, "WOMPI_IVA_PCT", 19),
        "dias_liquidacion": getattr(settings, "DIAS_LIQUIDACION", 5),
        "vendedor_actual": vendedor,
        "cliente_actual": cliente,
        "comprador_actual": comprador,
        "visitas_sitio": CuentaPlataforma.objects.filter(pk=1).values_list("visitas", flat=True).first() or 0,
    }
