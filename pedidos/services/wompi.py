import hashlib
import hmac
import json
import time

from django.conf import settings


def nueva_referencia(pedido_id):
    return f"PEDIDO-{pedido_id}-{int(time.time())}"


def monto_centavos(pedido):
    cop = int(round(float(pedido.monto_cop or pedido.producto.precio_final_cop)))
    return max(cop, 0) * 100


def _cuenta():
    from pedidos.models import CuentaPlataforma
    return CuentaPlataforma.objects.order_by("id").first()


def claves_wompi():
    cuenta = _cuenta()
    publica = (cuenta.wompi_publica if cuenta and cuenta.wompi_publica else "") or getattr(settings, "WOMPI_PUBLIC_KEY", "")
    integridad = (cuenta.wompi_integridad if cuenta and cuenta.wompi_integridad else "") or getattr(settings, "WOMPI_INTEGRITY_SECRET", "")
    eventos = (cuenta.wompi_eventos if cuenta and cuenta.wompi_eventos else "") or getattr(settings, "WOMPI_EVENTS_SECRET", "")
    return publica or "", integridad or "", eventos or ""


def firma_integridad(referencia, amount_in_cents, currency="COP"):
    secreto = claves_wompi()[1]
    raw = f"{referencia}{amount_in_cents}{currency}{secreto}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def checkout_listo():
    return bool(claves_wompi()[0])


def contexto_widget(pedido, redirect_url):
    cents = monto_centavos(pedido)
    ref = pedido.referencia_pago
    return {
        "public_key": claves_wompi()[0],
        "reference": ref,
        "amount_in_cents": cents,
        "currency": "COP",
        "signature": firma_integridad(ref, cents),
        "redirect_url": redirect_url,
        "checkout_url": getattr(settings, "WOMPI_CHECKOUT_URL", "https://checkout.wompi.co/p/"),
        "customer_email": pedido.cliente_email or "",
    }


def evento_valido(payload, checksum):
    secreto = claves_wompi()[2]
    if not secreto or not checksum:
        return True
    props = payload.get("signature", {}).get("properties") or []
    tx = (payload.get("data") or {}).get("transaction") or {}
    partes = []
    for path in props:
        cur = {"transaction": tx}
        for bit in path.split("."):
            cur = (cur or {}).get(bit) if isinstance(cur, dict) else None
        partes.append("" if cur is None else str(cur))
    ts = str(payload.get("timestamp") or "")
    raw = "".join(partes) + ts + secreto
    esperado = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hmac.compare_digest(esperado, checksum)


def extraer_transaccion(body):
    if isinstance(body, (bytes, str)):
        body = json.loads(body)
    return (body.get("data") or {}).get("transaction") or body.get("transaction") or {}
