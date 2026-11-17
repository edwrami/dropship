"""Flete de un viaje completo, igual que en ERagro.

Kilómetros de vía = distancia en línea recta × 1,3. Se suma el costo por
kilómetro y 2 horas de cargue más 2 de descargue. El mínimo es $80.000.
Quien vende elige si lo paga quien compra, quien vende o los dos por mitad.
"""
from decimal import Decimal, ROUND_HALF_UP

ROAD_FACTOR = Decimal("1.3")
PER_KM = Decimal("4200")
HOUR = Decimal("18500")
LOAD_HOURS = Decimal("2")
UNLOAD_HOURS = Decimal("2")
MINIMUM = Decimal("80000")


def _peso(value):
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _punto(obj):
    if obj is None:
        return None
    lat = getattr(obj, "lat", None)
    lng = getattr(obj, "lng", None)
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def _km(origen, destino):
    from math import asin, cos, radians, sin, sqrt
    lat1, lng1 = origen
    lat2, lng2 = destino
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    recta = 2 * 6371 * asin(min(1, sqrt(h)))
    km = max(Decimal("1"), (Decimal(str(recta)) * ROAD_FACTOR).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return km


def cotizar(origen, destino, paga):
    punto_origen = _punto(origen)
    punto_destino = _punto(destino)
    if not punto_origen or not punto_destino:
        return None
    km = _km(punto_origen, punto_destino)
    movilizacion = _peso(km * PER_KM)
    espera = _peso((LOAD_HOURS + UNLOAD_HOURS) * HOUR)
    flete = max(MINIMUM, movilizacion + espera)
    quien = paga if paga in ("vendedor", "mitad", "comprador") else "comprador"
    if quien == "vendedor":
        comprador, vendedor = Decimal("0"), flete
    elif quien == "mitad":
        comprador = _peso(flete / 2)
        vendedor = flete - comprador
    else:
        comprador, vendedor = flete, Decimal("0")
    return {
        "km": km,
        "freight": flete,
        "payer": quien,
        "buyer_part": comprador,
        "seller_part": vendedor,
    }


def sumar_flete(pedido, vendedor, destino):
    """Suma el flete calculado. La comisión no se recalcula sobre el flete."""
    if vendedor is None or destino is None:
        return pedido
    viaje = cotizar(vendedor, destino, getattr(vendedor, "paga_flete", "") or "comprador")
    if not viaje:
        return pedido
    from vendedores.services import tarifa_wompi
    anterior = Decimal(pedido.envio_cop or 0)
    pedido.flete_cop = viaje["freight"]
    pedido.flete_km = viaje["km"]
    pedido.flete_paga = viaje["payer"]
    pedido.flete_vendedor_cop = viaje["seller_part"]
    pedido.envio_cop = viaje["buyer_part"]
    pedido.modo_envio = "flete"
    pedido.monto_cop = Decimal(pedido.monto_cop or 0) - anterior + viaje["buyer_part"]
    conocida = Decimal(pedido.tarifa_pasarela_cop or 0)
    for _ in range(4):
        nueva = tarifa_wompi(pedido.monto_cop)
        extra = nueva - conocida
        pedido.tarifa_pasarela_cop = nueva
        if extra <= 0:
            break
        pedido.monto_cop += extra
        conocida = nueva
    neto = Decimal(pedido.neto_vendedor or 0) - viaje["seller_part"]
    pedido.neto_vendedor = neto if neto > 0 else Decimal("0")
    return pedido
