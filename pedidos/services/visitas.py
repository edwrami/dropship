from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F

from pedidos.models import CuentaPlataforma
from productos.models import Producto
from vendedores.models import Vendedor


def _es_dueno(request, vendedor_id):
    if not vendedor_id or not request.user.is_authenticated:
        return False
    try:
        return request.user.vendedor.pk == vendedor_id
    except ObjectDoesNotExist:
        return False


def registrar_visita(request, vendedor_id=None, producto_id=None):
    """Suma una visita por navegador. Recargar la misma página no vuelve a sumar."""
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False) and user.is_staff:
        return set()
    if _es_dueno(request, vendedor_id):
        vendedor_id = None
    vistas = list(request.session.get("vistas") or [])
    hechas = set()
    if "sitio" not in vistas:
        cuenta, _creada = CuentaPlataforma.objects.get_or_create(pk=1)
        CuentaPlataforma.objects.filter(pk=cuenta.pk).update(visitas=F("visitas") + 1)
        vistas.append("sitio")
        hechas.add("sitio")
    if vendedor_id:
        clave = f"v{vendedor_id}"
        if clave not in vistas:
            Vendedor.objects.filter(pk=vendedor_id).update(visitas=F("visitas") + 1)
            vistas.append(clave)
            hechas.add("vendedor")
    if producto_id:
        clave = f"p{producto_id}"
        if clave not in vistas:
            Producto.objects.filter(pk=producto_id).update(visitas=F("visitas") + 1)
            vistas.append(clave)
            hechas.add("producto")
    if hechas:
        request.session["vistas"] = vistas[-500:]
        request.session.modified = True
    return hechas
