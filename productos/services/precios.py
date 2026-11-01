from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings

TRM_APROX = Decimal(str(getattr(settings, "TRM_APROX", 4000)))

# Relación costo/beneficio: el flete no se come el producto y el precio
# de venta sigue siendo competitivo (no 4x–7x el costo).
COSTO_MIN_USD = 8.0
COSTO_MAX_USD = 70.0
RATIO_FLETE_MAX = 0.40
RATIO_VENTA_MAX = 2.20
GANANCIA_MIN_USD = 5.0


def calcular_precio_venta(producto):
    costo = Decimal(producto.precio_costo)
    peso = Decimal(producto.peso_libras)
    flete = peso * Decimal(str(settings.FLETE_POR_LIBRA_USD))

    cif = costo + flete

    iva = Decimal("0")
    if cif > Decimal(settings.UMBRAL_IVA_USD):
        iva = cif * Decimal(str(settings.IVA_COLOMBIA))

    subtotal = cif + iva
    margen = subtotal * (Decimal(producto.margen_pct) / Decimal("100"))
    precio_venta_usd = subtotal + margen

    return {
        "costo_usd": float(costo),
        "flete_usd": float(flete),
        "cif_usd": float(cif),
        "iva_usd": float(iva),
        "margen_usd": float(margen),
        "precio_venta_usd": round(float(precio_venta_usd), 2),
        "precio_final_cop": round(float(precio_venta_usd) * float(TRM_APROX), 0),
    }


def evaluar_negocio(costo, peso, margen_pct=None, precio_mercado=None):
    """True si el precio final es rentable y sigue siendo razonable frente al costo."""
    margen_pct = margen_pct if margen_pct is not None else getattr(settings, "MARGEN_DEFAULT", 40)
    costo_f = float(costo)
    if costo_f < COSTO_MIN_USD or costo_f > COSTO_MAX_USD:
        return False, None
    fake = SimpleNamespace(
        precio_costo=costo,
        peso_libras=peso,
        margen_pct=margen_pct,
    )
    calc = calcular_precio_venta(fake)
    flete = calc["flete_usd"]
    venta = calc["precio_venta_usd"]
    ganancia = venta - costo_f - flete - calc["iva_usd"]
    if flete / costo_f > RATIO_FLETE_MAX:
        return False, calc
    if venta / costo_f > RATIO_VENTA_MAX:
        return False, calc
    if ganancia < GANANCIA_MIN_USD:
        return False, calc
    if precio_mercado:
        mercado = float(precio_mercado)
        if mercado > 0 and venta > mercado * 0.90:
            return False, calc
    return True, calc
