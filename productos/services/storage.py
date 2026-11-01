import json
import mimetypes
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BUCKET = "productos"
TIPOS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_BYTES = 5 * 1024 * 1024
_publico = False


def _clave():
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _base():
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def _pedir(metodo, ruta, cuerpo=None, tipo=None, extra=None):
    headers = {
        "Authorization": "Bearer " + _clave(),
        "apikey": _clave(),
    }
    if tipo:
        headers["Content-Type"] = tipo
    if extra:
        headers.update(extra)
    data = cuerpo if isinstance(cuerpo, (bytes, bytearray)) or cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    if cuerpo is not None and not isinstance(cuerpo, (bytes, bytearray)) and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
    req = Request(_base() + ruta, data=data, headers=headers, method=metodo)
    try:
        with urlopen(req, timeout=40) as resp:
            raw = resp.read()
            return resp.status, raw
    except HTTPError as exc:
        return exc.code, exc.read()


def asegurar_bucket_publico():
    global _publico
    if _publico:
        return
    codigo, raw = _pedir("GET", f"/storage/v1/bucket/{BUCKET}")
    if codigo == 404:
        _pedir("POST", "/storage/v1/bucket", {
            "id": BUCKET,
            "name": BUCKET,
            "public": True,
            "file_size_limit": MAX_BYTES,
            "allowed_mime_types": list(TIPOS),
        })
    elif codigo == 200:
        info = json.loads(raw.decode("utf-8") or "{}")
        if not info.get("public"):
            _pedir("PUT", f"/storage/v1/bucket/{BUCKET}", {
                "public": True,
                "file_size_limit": MAX_BYTES,
                "allowed_mime_types": list(TIPOS),
            })
    _publico = True


def url_publica(ruta):
    return f"{_base()}/storage/v1/object/public/{BUCKET}/{ruta}"


def subir_foto(contenido, ruta, tipo):
    asegurar_bucket_publico()
    codigo, raw = _pedir(
        "POST",
        f"/storage/v1/object/{BUCKET}/{ruta}",
        contenido,
        tipo,
        {"x-upsert": "true"},
    )
    if codigo not in (200, 201):
        detalle = raw.decode("utf-8", "replace")[:180]
        raise RuntimeError(f"No se pudo guardar la foto ({codigo}). {detalle}")
    return url_publica(ruta)


def borrar_foto(ruta):
    if not ruta:
        return
    _pedir("DELETE", f"/storage/v1/object/{BUCKET}/{ruta}")


def extension(archivo):
    tipo = (archivo.content_type or "").split(";")[0].strip().lower()
    if tipo not in TIPOS:
        adivinado = mimetypes.guess_type(archivo.name or "")[0]
        tipo = adivinado if adivinado in TIPOS else ""
    if tipo not in TIPOS:
        raise ValueError("Usa fotos JPG, PNG o WEBP.")
    if archivo.size > MAX_BYTES:
        raise ValueError("Cada foto puede pesar hasta 5 MB.")
    return TIPOS[tipo], tipo
