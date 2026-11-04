from decimal import Decimal, InvalidOperation
from itertools import zip_longest

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from vendedores.models import Categoria
from vendedores.opciones import CONDICIONES, DEPARTAMENTOS, ENTREGAS, RANGOS, TIPOS
from vendedores.services import aplicar_sanciones

from .models import Producto
from .services.aliexpress import extraer_producto_aliexpress
from .services.outlets import extraer_producto_outlet


def _catalogo():
    return (
        Producto.objects.filter(activo=True)
        .filter(Q(controla_stock=False) | Q(stock__gt=0))
        .filter(Q(vendedor__isnull=True) | Q(vendedor__estado="activo"))
        .select_related("rubro", "rubro__padre", "vendedor")
        .prefetch_related("fotos")
    )


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _decimal(valor):
    try:
        return Decimal(str(valor).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


_CLAVES_FILTRO = (
    "q", "categoria", "ciudad", "departamento", "tipo", "rango",
    "precio_min", "precio_max", "condicion", "entrega", "marca",
    "color", "talla", "envio", "garantia", "orden",
)


def hay_filtros(request):
    g = request.GET
    return any((g.get(clave) or "").strip() for clave in _CLAVES_FILTRO)


def catalogo_filtrado(request):
    qs = _catalogo()
    g = request.GET
    q = (g.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(titulo__icontains=q)
            | Q(descripcion__icontains=q)
            | Q(marca__icontains=q)
            | Q(categoria__icontains=q)
            | Q(rubro__nombre__icontains=q)
            | Q(color__icontains=q)
            | Q(sku__icontains=q)
            | Q(ciudad_despacho__icontains=q)
            | Q(vendedor__nombre_tienda__icontains=q)
        )

    cid = _entero(g.get("categoria"))
    if cid:
        cat = Categoria.objects.filter(pk=cid).first()
        if cat:
            if cat.padre_id:
                qs = qs.filter(rubro=cat)
            else:
                qs = qs.filter(Q(rubro=cat) | Q(rubro__padre=cat))

    ciudad = (g.get("ciudad") or "").strip()
    if ciudad:
        qs = qs.filter(
            Q(ciudad_despacho__icontains=ciudad) | Q(vendedor__ciudad__icontains=ciudad)
        )

    departamento = (g.get("departamento") or "").strip()
    if departamento:
        qs = qs.filter(
            Q(departamento_despacho=departamento) | Q(vendedor__departamento=departamento)
        )

    tipo = (g.get("tipo") or "").strip()
    if tipo:
        qs = qs.filter(vendedor__tipo=tipo)

    rango = (g.get("rango") or "").strip()
    if rango:
        qs = qs.filter(banda_precio=rango)

    precio_min = _decimal(g.get("precio_min"))
    if precio_min is not None:
        qs = qs.filter(precio_final_cop__gte=precio_min)
    precio_max = _decimal(g.get("precio_max"))
    if precio_max is not None:
        qs = qs.filter(precio_final_cop__lte=precio_max)

    condicion = (g.get("condicion") or "").strip()
    if condicion:
        qs = qs.filter(condicion=condicion)

    entrega = _entero(g.get("entrega"))
    if entrega:
        qs = qs.filter(tiempo_entrega_max__lte=entrega, tiempo_entrega_max__isnull=False)

    if g.get("envio") == "1":
        qs = qs.filter(envio_gratis=True)
    if g.get("garantia") == "1":
        qs = qs.filter(garantia_dias__gte=1)

    marca = (g.get("marca") or "").strip()
    if marca:
        qs = qs.filter(marca__icontains=marca)
    color = (g.get("color") or "").strip()
    if color:
        qs = qs.filter(color__icontains=color)
    talla = (g.get("talla") or "").strip()
    if talla:
        qs = qs.filter(talla__iexact=talla)

    orden = g.get("orden") or "recientes"
    if orden == "precio_asc":
        qs = qs.order_by("precio_final_cop", "-creado")
    elif orden == "precio_desc":
        qs = qs.order_by("-precio_final_cop", "-creado")
    elif orden == "entrega":
        qs = qs.order_by("tiempo_entrega_max", "-creado")
    else:
        qs = qs.order_by("-creado")
    return qs


def opciones_busqueda():
    return {
        "grupos": Categoria.objects.filter(padre__isnull=True).prefetch_related("hijos"),
        "departamentos": DEPARTAMENTOS,
        "tipos": TIPOS,
        "rangos": RANGOS,
        "condiciones": CONDICIONES,
        "entregas": ENTREGAS,
    }


def mezcla_carrusel(qs, limite=8):
    """Económicos y buscados, de una tienda o de varias, sin repetir."""
    baratos = list(qs.order_by("precio_final_cop", "-visitas")[:limite])
    buscados = list(qs.order_by("-visitas", "precio_final_cop")[:limite])
    vistos = []
    ids = set()
    for pareja in zip_longest(buscados, baratos):
        for producto in pareja:
            if producto is not None and producto.id not in ids:
                ids.add(producto.id)
                vistos.append(producto)
    return vistos


def _varias(productos):
    return len({producto.vendedor_id for producto in productos if producto.vendedor_id}) > 1


def vitrina_comprador(request):
    """Productos del panel. Con filtros, respeta la búsqueda. Sin filtros, mezcla el catálogo al azar."""
    qs = catalogo_filtrado(request)
    params = request.GET.copy()
    params.pop("page", None)
    if hay_filtros(request):
        pagina = Paginator(qs, 24).get_page(request.GET.get("page"))
        productos = pagina.object_list
        total = pagina.paginator.count
        aleatorio = False
        carrusel = mezcla_carrusel(qs)
    else:
        pagina = None
        productos = list(qs.order_by("?")[:24])
        total = len(productos)
        aleatorio = True
        carrusel = mezcla_carrusel(_catalogo())
    datos = opciones_busqueda()
    datos.update({
        "productos": productos,
        "pagina": pagina,
        "total": total,
        "aleatorio": aleatorio,
        "filtros_qs": params.urlencode(),
        "carrusel": carrusel,
        "varias": _varias(carrusel),
    })
    return datos


def lista_productos(request):
    from pedidos.services.visitas import registrar_visita
    registrar_visita(request)
    aplicar_sanciones()
    qs = catalogo_filtrado(request)
    total = qs.count()
    pagina = Paginator(qs, 24).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    carrusel = mezcla_carrusel(_catalogo())
    ctx = opciones_busqueda()
    ctx.update({
        "productos": pagina,
        "total": total,
        "filtros_qs": params.urlencode(),
        "carrusel": carrusel,
        "varias": _varias(carrusel),
    })
    return render(request, "productos/lista.html", ctx)


def carrusel_facebook(request):
    from pedidos.services.visitas import registrar_visita
    registrar_visita(request)
    qs = _catalogo()
    slug = (request.GET.get("tienda") or "").strip()
    tienda = None
    if slug:
        from vendedores.models import Vendedor
        tienda = Vendedor.objects.filter(slug=slug, estado="activo").first()
        qs = qs.filter(vendedor=tienda) if tienda is not None else qs.none()
    carrusel = mezcla_carrusel(qs, 12)
    return render(request, "productos/facebook.html", {
        "carrusel": carrusel,
        "tienda": tienda,
        "varias": tienda is None and _varias(carrusel),
    })


def agregar_producto(request):
    if request.method == "POST":
        url = request.POST.get("url", "").strip()
        margen = request.POST.get("margen") or 40
        peso = request.POST.get("peso") or 1
        costo_manual = request.POST.get("precio_costo", "").strip()
        titulo_manual = request.POST.get("titulo", "").strip()

        if "aliexpress." in url:
            datos = extraer_producto_aliexpress(url)
            origen = "aliexpress"
        else:
            datos = extraer_producto_outlet(url)
            origen = "outlet"

        if "error" in datos:
            if not costo_manual and not titulo_manual:
                return render(request, "productos/agregar.html", {"error": datos["error"]})
            datos = {
                "id_externo": url[-80:],
                "titulo": titulo_manual or "Producto",
                "precio_costo": 0,
                "moneda": "USD",
                "imagen": "",
                "url_origen": url,
                "tienda": origen,
            }

        if costo_manual:
            try:
                datos["precio_costo"] = float(costo_manual)
            except ValueError:
                return render(request, "productos/agregar.html", {"error": "Precio de costo inválido"})
        if titulo_manual:
            datos["titulo"] = titulo_manual

        Producto.objects.update_or_create(
            id_externo=datos["id_externo"],
            defaults={
                "origen": origen,
                "url_origen": url,
                "tienda": datos.get("tienda", ""),
                "titulo": datos["titulo"],
                "precio_costo": datos["precio_costo"],
                "moneda": datos.get("moneda", "USD"),
                "imagen": datos.get("imagen", ""),
                "margen_pct": margen,
                "peso_libras": peso,
            },
        )
        return redirect("lista_productos")

    return render(request, "productos/agregar.html")


def detalle_producto(request, pk):
    producto = get_object_or_404(
        Producto.objects.select_related("rubro", "rubro__padre", "vendedor").prefetch_related("fotos"),
        pk=pk,
        activo=True,
    )
    if producto.vendedor_id and producto.vendedor.estado != "activo":
        raise Http404("Producto no disponible")
    if producto.controla_stock and producto.stock <= 0:
        raise Http404("Producto agotado")
    from django.core.exceptions import ObjectDoesNotExist
    from django.db.models import Avg, Count

    from pedidos.services.visitas import registrar_visita
    producto_id = producto.pk
    if producto.vendedor_id and request.user.is_authenticated:
        try:
            if request.user.vendedor.pk == producto.vendedor_id:
                producto_id = None
        except ObjectDoesNotExist:
            pass
    if "producto" in registrar_visita(request, producto_id=producto_id):
        producto.visitas += 1
    nota_tienda = None
    total_notas = 0
    if producto.vendedor_id:
        notas = producto.vendedor.calificaciones.aggregate(promedio=Avg("estrellas"), total=Count("id"))
        nota_tienda = producto.vendedor.calificacion_manual
        if nota_tienda is None:
            nota_tienda = notas["promedio"]
        total_notas = notas["total"]
    ve_mayor = False
    cliente = None
    if request.user.is_authenticated:
        from vendedores.models import ClienteTienda, Conexion
        try:
            cliente = request.user.cliente_tienda
        except ClienteTienda.DoesNotExist:
            cliente = None
        if cliente and producto.vendedor_id and producto.precio_mayor_cop:
            ve_mayor = Conexion.objects.filter(
                cliente=cliente, proveedor_id=producto.vendedor_id,
            ).exists()
    return render(request, "productos/detalle.html", {
        "producto": producto,
        "error": "",
        "ve_mayor": ve_mayor,
        "nota_tienda": nota_tienda,
        "total_notas": total_notas,
    })


def estado_producto(request, pk):
    producto = get_object_or_404(
        Producto.objects.select_related("rubro", "vendedor"),
        pk=pk,
        activo=True,
    )
    if producto.vendedor_id and producto.vendedor.estado != "activo":
        raise Http404("Producto no disponible")
    kicker = producto.ciudad_despacho or "ERA shop"
    if producto.vendedor_id:
        kicker = f"{producto.vendedor.nombre_tienda} · {kicker}"
    return render(request, "compartir/estado.html", {
        "modo": "producto",
        "titulo": producto.titulo,
        "kicker": kicker,
        "precio": f"${producto.precio_vigente:,.0f} COP".replace(",", "."),
        "detalle": producto.entrega_texto or "Pide en ERA shop",
        "enlace": reverse("detalle_producto", args=[producto.pk]),
        "imagen": producto.imagen,
    })
