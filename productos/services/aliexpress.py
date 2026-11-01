import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings

APIFY_ACTOR = "epctex~aliexpress-scraper"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def extraer_producto_aliexpress(url):
    if getattr(settings, "APIFY_TOKEN", ""):
        datos = _via_apify(url)
        if "error" not in datos:
            return datos
    return _via_html(url)


def _via_apify(url):
    endpoint = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
    payload = {"startUrls": [{"url": url}], "maxItems": 1}
    headers = {"Authorization": f"Bearer {settings.APIFY_TOKEN}"}
    try:
        r = requests.post(endpoint, json=payload, headers=headers, timeout=120)
    except Exception as e:
        return {"error": f"Fallo de conexión Apify: {e}"}
    if r.status_code != 200:
        return {"error": f"Apify {r.status_code}: {r.text[:200]}"}
    items = r.json()
    if not items:
        return {"error": "Sin resultados en Apify"}
    it = items[0]
    return {
        "id_externo": str(it.get("id") or it.get("productId") or _id_de_url(url)),
        "titulo": it.get("title", "Sin título"),
        "precio_costo": float(it.get("price", 0) or 0),
        "moneda": it.get("currency", "USD"),
        "imagen": (it.get("images") or [""])[0],
        "url_origen": url,
        "tienda": "AliExpress",
    }


def _via_html(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as e:
        return {"error": f"No se pudo abrir AliExpress: {e}"}

    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    data = _json_embebido(html) or {}

    titulo = (
        _buscar(data, "subject", "title", "name")
        or _meta(soup, "og:title")
        or (soup.title.string if soup.title else "")
        or "Producto AliExpress"
    )
    imagen = (
        _buscar(data, "image", "imageUrl", "ogImage")
        or _primera_lista(data, "images", "imagePathList")
        or _meta(soup, "og:image")
        or ""
    )
    precio = _precio(data) or _precio_texto(html) or _precio_meta(soup)
    moneda = _buscar(data, "currency", "currencyCode") or "USD"
    product_id = str(
        _buscar(data, "productId", "itemId", "id") or _id_de_url(url)
    )

    if not titulo and not precio:
        return {"error": "AliExpress no devolvió datos públicos. Use carga manual (precio)."}

    return {
        "id_externo": product_id,
        "titulo": str(titulo).strip()[:400],
        "precio_costo": float(precio or 0),
        "moneda": str(moneda)[:5],
        "imagen": str(imagen),
        "url_origen": url,
        "tienda": "AliExpress",
    }


def _id_de_url(url):
    m = re.search(r"/item/(\d+)", url)
    if m:
        return m.group(1)
    return urlparse(url).path.strip("/").replace("/", "_")[-80:] or url[-40:]


def _meta(soup, prop):
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    return tag["content"] if tag and tag.get("content") else ""


def _json_embebido(html):
    for pat in (
        r"window\.runParams\s*=\s*({.*?});",
        r"window\.__INIT_DATA__\s*=\s*({.*?});",
        r'"data"\s*:\s*({.*?})\s*,\s*"csrfToken"',
    ):
        m = re.search(pat, html, re.DOTALL)
        if not m:
            continue
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
    blobs = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for blob in blobs:
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and (obj.get("name") or obj.get("offers")):
            return obj
    return {}


def _buscar(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for k in keys:
        if obj.get(k):
            return obj[k]
    for v in obj.values():
        if isinstance(v, dict):
            found = _buscar(v, *keys)
            if found:
                return found
    return None


def _primera_lista(obj, *keys):
    val = _buscar(obj, *keys)
    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url") or first.get("src") or ""
    return ""


def _precio(obj):
    for key in ("formatedActivityPrice", "formatedPrice", "price", "salePrice", "minPrice", "lowPrice"):
        val = _buscar(obj, key)
        n = _a_float(val)
        if n:
            return n
    offers = obj.get("offers") if isinstance(obj, dict) else None
    if isinstance(offers, dict):
        return _a_float(offers.get("price") or offers.get("lowPrice"))
    if isinstance(offers, list) and offers:
        return _a_float(offers[0].get("price"))
    return 0.0


def _precio_meta(soup):
    return _a_float(_meta(soup, "product:price:amount") or _meta(soup, "og:price:amount"))


def _precio_texto(html):
    m = re.search(r'"salePrice"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?', html)
    if m:
        return _a_float(m.group(1))
    m = re.search(r'"actMinPrice"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?', html)
    if m:
        return _a_float(m.group(1))
    return 0.0


def _a_float(val):
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = re.sub(r"[^\d.,]", "", str(val)).replace(",", ".")
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0
