import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0 Safari/537.36")
}


def extraer_producto_outlet(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return {"error": f"No accesible: {e}"}

    soup = BeautifulSoup(r.text, "html.parser")

    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag["content"] if tag and tag.get("content") else ""

    titulo = meta("og:title") or (soup.title.string if soup.title else "")
    imagen = meta("og:image")
    precio = meta("product:price:amount") or meta("og:price:amount")
    moneda = meta("product:price:currency") or "USD"

    try:
        precio = float(precio)
    except (TypeError, ValueError):
        precio = 0.0

    return {
        "id_externo": urlparse(url).path.strip("/").replace("/", "_")[-100:] or url[-40:],
        "titulo": titulo.strip() or "Sin título",
        "precio_costo": precio,
        "moneda": moneda,
        "imagen": imagen,
        "url_origen": url,
        "tienda": urlparse(url).netloc,
    }
