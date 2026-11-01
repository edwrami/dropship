import requests
from django.conf import settings


def crear_orden_dsers(dsers_product_id, variante, direccion):
    if not settings.DSERS_API_KEY:
        return {"error": "Falta DSERS_API_KEY"}

    url = f"{settings.DSERS_BASE_URL}/api/v1/orders"
    headers = {
        "Authorization": f"Bearer {settings.DSERS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "productId": dsers_product_id,
        "variant": variante,
        "shipping": {
            "name": direccion["nombre"],
            "phone": direccion["telefono"],
            "address": direccion["direccion"],
            "city": direccion["ciudad"],
            "country": "CO",
        },
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
    except Exception as e:
        return {"error": f"Fallo conexión DSers: {e}"}

    if r.status_code not in (200, 201):
        return {"error": f"DSers {r.status_code}: {r.text[:200]}"}
    return r.json()
