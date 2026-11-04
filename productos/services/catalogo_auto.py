import logging
import re
import time
from urllib.parse import quote_plus, unquote, urljoin

from django.conf import settings

from productos.categorias_es import traducir_categoria
from productos.models import Producto
from productos.services.precios import evaluar_negocio

log = logging.getLogger("dropship.sync")

try:
    from curl_cffi import requests as http
    IMPERSONATE = "chrome131"
except ImportError:
    import requests as http
    IMPERSONATE = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}

BUSQUEDAS = [
    "led lamp",
    "bluetooth headphones",
    "smart watch",
    "desk organizer",
    "wireless charger",
    "phone case",
    "night light",
    "thermos bottle",
]

POR_BUSQUEDA = 8
CATALOGO_MINIMO = 20
# Lo que pagamos al mayorista vs. precio de vitrina (AliExpress típico).
COSTO_MAYORISTA_PCT = 0.38

PESO_CATEGORIA = {
    "mobile-accessories": 0.25,
    "mens-watches": 0.30,
    "womens-watches": 0.30,
    "smartphones": 0.45,
    "tablets": 0.70,
    "laptops": 2.40,
    "home-decoration": 0.55,
    "kitchen-accessories": 0.70,
    "sports-accessories": 0.90,
    "sunglasses": 0.20,
}

_session = None


def _cliente():
    global _session
    if _session is None:
        if IMPERSONATE:
            _session = http.Session(impersonate=IMPERSONATE)
        else:
            _session = http.Session()
        _session.headers.update(HEADERS)
        try:
            _session.get("https://www.aliexpress.com/", timeout=25)
        except Exception:
            log.warning("No se pudo abrir AliExpress (inicio de sesión HTTP)")
    return _session


def _html_bloqueado(html):
    return "_____tmd_____/punish" in (html or "") or "x5secdata" in (html or "")


def _peso(categoria, default=0.35):
    return PESO_CATEGORIA.get((categoria or "").strip().lower(), default)


def cargar_productos_nuevos():
    return 0
    """Busca mayorista, publica solo si flete+margen dejan un precio creíble."""
    quitados = _quitar_mal_negocio()
    publicados = 0
    bloqueado = False
    for q in BUSQUEDAS:
        if bloqueado:
            break
        try:
            items, bloqueado = buscar_aliexpress(q, POR_BUSQUEDA)
            log.info("Búsqueda '%s': %s candidatos", q, len(items))
        except Exception:
            log.exception("Búsqueda falló: %s", q)
            continue
        for item in items:
            if _publicar(item, categoria=q):
                publicados += 1
        time.sleep(1.0)
    activos = Producto.objects.filter(activo=True).count()
    if activos < CATALOGO_MINIMO:
        extra = _cargar_respaldo()
        publicados += extra
        log.info("Catálogo de respaldo (buen negocio): %s", extra)
    log.info("Publicados: %s | retirados por mal C/B: %s", publicados, quitados)
    return publicados


def buscar_aliexpress(query, limite=8):
    from bs4 import BeautifulSoup

    s = _cliente()
    q = quote_plus(query.strip())
    url = f"https://www.aliexpress.com/wholesale?SearchText={q}"
    r = s.get(url, timeout=30, allow_redirects=True)
    r.raise_for_status()
    html = r.text
    if _html_bloqueado(html):
        try:
            s.get("https://www.aliexpress.com/", timeout=25)
            r = s.get(url, timeout=30, allow_redirects=True)
            r.raise_for_status()
            html = r.text
        except Exception:
            return [], True
        if _html_bloqueado(html):
            log.warning("AliExpress bloqueó la búsqueda: %s", query)
            return [], True
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a.search-card-item") or soup.select('a[href*="/item/"]')
    out = []
    vistos = set()
    peso = _peso(query, 0.35)
    for a in cards:
        href = a.get("href") or ""
        pid = _id_producto(href)
        if not pid or pid in vistos:
            continue
        vistos.add(pid)
        precio = _precio_usd(href)
        ok, _calc = evaluar_negocio(precio, peso)
        if not ok:
            continue
        img = a.find("img")
        titulo = ""
        imagen = ""
        if img:
            titulo = (img.get("alt") or "").strip()
            imagen = img.get("src") or img.get("data-src") or ""
        if not titulo:
            titulo = (a.get("title") or "").strip() or a.get_text(" ", strip=True) or query
        item_url = f"https://www.aliexpress.com/item/{pid}.html"
        out.append({
            "id_externo": pid,
            "titulo": (titulo or f"Producto {pid}")[:400],
            "precio_costo": round(precio, 2),
            "moneda": "USD",
            "imagen": _abs_img(imagen),
            "url_origen": item_url,
            "tienda": "AliExpress",
            "origen": "aliexpress",
            "peso_libras": peso,
        })
        if len(out) >= limite:
            break
    return out, False


def _cargar_respaldo():
    """Mayorista: el precio de vitrina se usa como mercado; el costo es ~38%."""
    publicados = 0
    categorias = [
        "mobile-accessories",
        "mens-watches",
        "womens-watches",
        "smartphones",
        "sunglasses",
        "tablets",
        "home-decoration",
        "laptops",
        "kitchen-accessories",
        "sports-accessories",
    ]
    productos = []
    try:
        import requests as req_plain
        for cat in categorias:
            r = req_plain.get(
                f"https://dummyjson.com/products/category/{cat}?limit=20",
                timeout=25,
            )
            r.raise_for_status()
            productos.extend(r.json().get("products") or [])
    except Exception:
        log.exception("No se pudo leer el catálogo de respaldo")
        return 0
    for p in productos:
        mercado = float(p.get("price") or 0)
        rating = float(p.get("rating") or 0)
        if rating and rating < 3.7:
            continue
        costo = round(mercado * COSTO_MAYORISTA_PCT, 2)
        cat = str(p.get("category") or "")[:100]
        peso = _peso(cat)
        ok, _calc = evaluar_negocio(costo, peso, precio_mercado=mercado)
        if not ok:
            continue
        titulo = (p.get("title") or "").strip()
        if not titulo:
            continue
        thumbs = p.get("images") or []
        imagen = (thumbs[0] if thumbs else "") or p.get("thumbnail") or ""
        pid = str(p.get("id"))
        item = {
            "id_externo": f"mayorista-{pid}",
            "titulo": titulo[:400],
            "precio_costo": costo,
            "moneda": "USD",
            "imagen": str(imagen)[:800],
            "url_origen": f"https://dummyjson.com/products/{pid}",
            "tienda": "Mayorista",
            "origen": "alibaba",
            "peso_libras": peso,
            "descripcion": (
                f"Costo mayorista ${costo:.2f} USD. "
                f"Referencia de mercado ${mercado:.2f} USD."
            ),
        }
        if _publicar(item, categoria=cat):
            publicados += 1
        if publicados >= 36:
            break
    return publicados


def _quitar_mal_negocio():
    from pedidos.models import Pedido

    n = 0
    for prod in Producto.objects.filter(activo=True):
        ok, _calc = evaluar_negocio(prod.precio_costo, prod.peso_libras, prod.margen_pct)
        if ok:
            continue
        if Pedido.objects.filter(producto=prod).exists():
            prod.activo = False
            prod.save(update_fields=["activo"])
        else:
            prod.delete()
        n += 1
    return n


def _publicar(item, categoria=""):
    if Producto.objects.filter(id_externo=item["id_externo"]).exists():
        return False
    peso = item.get("peso_libras") or _peso(categoria)
    ok, _calc = evaluar_negocio(item["precio_costo"], peso)
    if not ok:
        return False
    margen = getattr(settings, "MARGEN_DEFAULT", 40)
    nombre = traducir_categoria(categoria)
    from vendedores.models import Categoria
    rubro = Categoria.objects.filter(nombre__iexact=nombre).order_by("padre_id").first() if nombre else None
    Producto.objects.create(
        origen=item.get("origen") or "aliexpress",
        id_externo=item["id_externo"],
        url_origen=item["url_origen"],
        tienda=item.get("tienda") or "AliExpress",
        titulo=item["titulo"],
        descripcion=item.get("descripcion") or "",
        imagen=item.get("imagen") or "",
        categoria=nombre or categoria,
        rubro=rubro,
        precio_costo=item["precio_costo"],
        moneda=item.get("moneda") or "USD",
        peso_libras=peso,
        margen_pct=margen,
        activo=True,
    )
    return True


def _id_producto(href):
    m = re.search(r"/item/(\d{8,})", href or "")
    if m:
        return m.group(1)
    m = re.search(r"productIds=(\d{8,})", href or "")
    if m:
        return m.group(1)
    return None


def _precio_usd(href):
    raw = unquote(href or "")
    m = re.search(r"pdp_npi=([^&]+)", raw)
    if not m:
        return 0.0
    parts = [p for p in m.group(1).split("!") if p]
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except ValueError:
            continue
    if not nums:
        return 0.0
    usd = [n for n in nums if 0.5 < n < 500]
    if usd:
        return usd[-1]
    cop = nums[-1]
    trm = float(getattr(settings, "TRM_APROX", 4000))
    return round(cop / trm, 2) if trm else 0.0


def _abs_img(src):
    if not src:
        return ""
    src = src.split("_.avif")[0]
    if src.startswith("//"):
        src = "https:" + src
    elif src.startswith("/"):
        src = urljoin("https://www.aliexpress.com", src)
    return src[:800]
