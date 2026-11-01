"""Nombres en español para los rubros que llegan en inglés del catálogo importado."""

TRADUCCION = {
    "mobile-accessories": "Audio y sonido",
    "mens-watches": "Relojes hombre",
    "womens-watches": "Relojes mujer",
    "smartphones": "Celulares y smartphones",
    "sunglasses": "Gafas",
    "tablets": "Tablets",
    "home-decoration": "Decoración",
    "laptops": "Portátiles",
    "kitchen-accessories": "Cocina y menaje",
    "sports-accessories": "Deportes y fitness",
    "led lamp": "Iluminación",
    "bluetooth headphones": "Audífonos",
    "smart watch": "Smartwatch y wearables",
    "desk organizer": "Organización y almacenamiento",
    "wireless charger": "Cables, cargadores y pilas",
    "phone case": "Cables, cargadores y pilas",
    "night light": "Iluminación",
    "thermos bottle": "Cocina y menaje",
}


def traducir_categoria(valor):
    texto = (valor or "").strip()
    if not texto:
        return ""
    clave = texto.lower().replace("_", " ").replace("-", " ")
    clave = " ".join(clave.split())
    por_espacio = {k.replace("-", " "): v for k, v in TRADUCCION.items()}
    return por_espacio.get(clave, texto)
