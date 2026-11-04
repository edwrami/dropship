import uuid

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from pedidos.models import Pedido
from productos.models import FotoProducto, Producto
from productos.services.storage import borrar_foto, extension, subir_foto

from .forms import DatosVendedorForm, ProductoVendedorForm, RegistroForm
from .models import Categoria, Vendedor
from .services import (
    aplicar_sanciones,
    cancelar_pedido_vendedor,
    reclasificar_vendedor,
)


def _grupos():
    return Categoria.objects.filter(padre__isnull=True).prefetch_related("hijos")


def _vendedor(user):
    if not user.is_authenticated:
        return None
    try:
        return user.vendedor
    except Vendedor.DoesNotExist:
        return None


def _ids_categorias(request):
    return [int(x) for x in request.POST.getlist("categorias") if str(x).isdigit()]


def _categorias_validas(ids):
    return list(Categoria.objects.filter(pk__in=ids, padre__isnull=False))


@transaction.atomic
def registro(request):
    if _vendedor(request.user):
        return redirect("panel_vendedor")
    form = RegistroForm(request.POST or None)
    seleccionadas = _ids_categorias(request) if request.method == "POST" else []
    if request.method == "POST" and form.is_valid():
        categorias = _categorias_validas(seleccionadas)
        if not categorias:
            form.add_error(None, "Elige al menos una categoría de mercancía.")
        else:
            data = form.cleaned_data
            user = User.objects.create_user(
                username=data["email"],
                email=data["email"],
                password=data["password"],
            )
            vendedor = Vendedor.objects.create(
                user=user,
                nombre_tienda=data["nombre_tienda"],
                responsable=data["responsable"],
                documento=data["documento"],
                telefono=data["telefono"],
                whatsapp=data["whatsapp"],
                nequi=data["nequi"],
                direccion=data["direccion"],
                ciudad=data["ciudad"].strip(),
                departamento=data["departamento"],
                tipo=data["tipo"],
                rango_precio=data["rango_precio"],
                acepta_terminos=True,
            )
            vendedor.categorias.set(categorias)
            login(request, user)
            messages.success(request, "Tienda creada. Ya puedes publicar mercancía.")
            return redirect("panel_vendedor")
    return render(request, "vendedores/registro.html", {
        "form": form,
        "grupos": _grupos(),
        "seleccionadas": seleccionadas,
    })


def entrar(request):
    if _vendedor(request.user):
        return redirect("panel_vendedor")
    error = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password") or "")
        if user is None:
            error = "Correo o contraseña incorrectos."
        else:
            login(request, user)
            if _vendedor(user) is None:
                logout(request)
                error = "Esa cuenta es de una tienda compradora. Entra desde Soy tienda."
            else:
                return redirect("panel_vendedor")
    return render(request, "vendedores/entrar.html", {"error": error})


def salir(request):
    logout(request)
    return redirect("lista_productos")


@login_required
def panel(request):
    aplicar_sanciones()
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("registro_vendedor")
    vendedor.refresh_from_db()
    productos = vendedor.productos.all()
    conexiones = vendedor.clientes_conectados.select_related("cliente") if vendedor.es_proveedor else []
    pedidos = vendedor.pedidos.select_related("producto", "giro").all()
    deuda = pedidos.filter(estado_comision__in=["pendiente", "reportada"]).aggregate(
        s=Sum("comision_cop")
    )["s"] or 0
    clientes = []
    vistos = set()
    for pedido in pedidos:
        clave = (pedido.cliente_documento or pedido.cliente_telefono, pedido.cliente_nombre)
        if clave in vistos:
            continue
        vistos.add(clave)
        clientes.append(pedido)
    notas = vendedor.calificaciones.aggregate(promedio=Avg("estrellas"), total=Count("id"))
    nota_publica = vendedor.calificacion_manual if vendedor.calificacion_manual is not None else notas["promedio"]
    return render(request, "vendedores/panel.html", {
        "vendedor": vendedor,
        "productos": productos,
        "pedidos": pedidos,
        "deuda": deuda,
        "conexiones": conexiones,
        "clientes": clientes,
        "nota_publica": nota_publica,
        "total_notas": notas["total"],
        "comentarios": vendedor.calificaciones.select_related("pedido").order_by("-creado")[:20],
    })


@login_required
def datos(request):
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("registro_vendedor")
    inicial = {
        "telefono": vendedor.telefono,
        "whatsapp": vendedor.whatsapp,
        "nequi": vendedor.nequi,
        "direccion": vendedor.direccion,
        "ciudad": vendedor.ciudad,
        "departamento": vendedor.departamento,
        "tipo": vendedor.tipo,
    }
    form = DatosVendedorForm(request.POST or None, initial=inicial)
    seleccionadas = (
        _ids_categorias(request)
        if request.method == "POST"
        else list(vendedor.categorias.values_list("id", flat=True))
    )
    if request.method == "POST" and form.is_valid():
        categorias = _categorias_validas(seleccionadas)
        if not categorias:
            form.add_error(None, "Elige al menos una categoría.")
        else:
            data = form.cleaned_data
            for campo in ("telefono", "whatsapp", "nequi", "direccion", "ciudad", "departamento", "tipo"):
                setattr(vendedor, campo, data[campo].strip() if isinstance(data[campo], str) else data[campo])
            vendedor.save()
            vendedor.categorias.set(categorias)
            from pedidos.services.giros import reintentar_pendientes
            reintentar_pendientes(vendedor)
            messages.success(request, "Clasificación actualizada.")
            return redirect("panel_vendedor")
    return render(request, "vendedores/datos.html", {
        "form": form,
        "grupos": _grupos(),
        "seleccionadas": seleccionadas,
        "vendedor": vendedor,
    })


@login_required
def producto_form(request, pk=None):
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("registro_vendedor")
    if vendedor.estado != "activo":
        messages.error(request, "Tu tienda fue retirada y no puede publicar.")
        return redirect("panel_vendedor")
    instancia = None
    if pk:
        instancia = get_object_or_404(Producto, pk=pk, vendedor=vendedor)
    form = ProductoVendedorForm(
        request.POST or None,
        instance=instancia,
        mayorista=vendedor.tipo in ("mayorista", "importador"),
    )
    archivos = request.FILES.getlist("fotos") if request.method == "POST" else []
    if request.method == "POST" and form.is_valid():
        if len(archivos) > 3:
            form.add_error(None, "Puedes subir hasta 3 fotos por producto.")
        elif not archivos and (instancia is None or not instancia.fotos.exists()):
            form.add_error(None, "Sube de 1 a 3 fotos del producto.")
        else:
            try:
                preparados = [extension(archivo) for archivo in archivos]
            except ValueError as exc:
                form.add_error(None, str(exc))
                preparados = None
        if form.errors:
            return render(request, "vendedores/producto_form.html", {"form": form, "producto": instancia})
        producto = form.save(commit=False)
        producto.vendedor = vendedor
        producto.origen = "vendedor"
        producto.tienda = vendedor.nombre_tienda
        producto.moneda = "COP"
        producto.margen_pct = 0
        producto.activo = True
        if not producto.precio_costo:
            producto.precio_costo = 0
        if not producto.id_externo:
            producto.id_externo = f"vend-{vendedor.id}-{uuid.uuid4().hex[:16]}"
        if not producto.url_origen:
            producto.url_origen = ""
        producto.save()
        if archivos:
            for anterior in list(producto.fotos.all()):
                borrar_foto(anterior.ruta)
                anterior.delete()
            primera = ""
            for i, archivo in enumerate(archivos, start=1):
                ext, tipo = preparados[i - 1]
                ruta = f"{vendedor.id}/{producto.id}/{i}-{uuid.uuid4().hex[:10]}.{ext}"
                archivo.seek(0)
                try:
                    url = subir_foto(archivo.read(), ruta, tipo)
                except RuntimeError as exc:
                    messages.error(request, str(exc))
                    return redirect("editar_producto", pk=producto.pk)
                FotoProducto.objects.create(producto=producto, url=url, ruta=ruta, orden=i)
                if not primera:
                    primera = url
            producto.imagen = primera
            producto.save(update_fields=["imagen"])
        reclasificar_vendedor(vendedor)
        messages.success(request, "Producto publicado con sus fotos.")
        return redirect("panel_vendedor")
    return render(request, "vendedores/producto_form.html", {"form": form, "producto": instancia})


@login_required
@require_POST
def ocultar_producto(request, pk):
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("registro_vendedor")
    producto = get_object_or_404(Producto, pk=pk, vendedor=vendedor)
    producto.activo = not producto.activo
    producto.save(update_fields=["activo"])
    reclasificar_vendedor(vendedor)
    return redirect("panel_vendedor")


@login_required
def liquidar(request):
    aplicar_sanciones()
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("registro_vendedor")
    vendedor.refresh_from_db()
    from django.conf import settings
    from pedidos.views import nequi_plataforma

    pendientes = vendedor.pedidos.filter(estado_comision="pendiente").select_related("producto")
    reportadas = vendedor.pedidos.filter(estado_comision="reportada").select_related("producto")
    por_confirmar = vendedor.pedidos.filter(estado_comision="por_confirmar").select_related("producto")
    deuda = pendientes.aggregate(s=Sum("comision_cop"))["s"] or 0
    error = ""
    if request.method == "POST":
        comp = (request.POST.get("comprobante") or "").strip()[:120]
        archivo = request.FILES.get("comprobante_foto")
        if vendedor.estado == "expulsado":
            error = "La tienda ya fue retirada. El pago de la deuda no la publica de nuevo: lo confirma el administrador."
        elif not pendientes.exists():
            error = "No hay comisiones pendientes por reportar."
        elif not comp:
            error = "Escribe el número o ID de la transferencia de la comisión."
        elif archivo is None:
            error = "Anexa la foto del comprobante de Nequi."
        else:
            try:
                ext, tipo = extension(archivo)
                archivo.seek(0)
                ruta = f"comisiones/{vendedor.id}/{uuid.uuid4().hex[:12]}.{ext}"
                url = subir_foto(archivo.read(), ruta, tipo)
            except (ValueError, RuntimeError) as exc:
                error = str(exc)
            else:
                pendientes.update(
                    estado_comision="reportada",
                    comprobante_comision=comp,
                    comprobante_url=url,
                    comprobante_ruta=ruta,
                )
                comp = ""
                messages.success(
                    request,
                    "Comprobante anexado. La comisión queda liquidada cuando ERA shop lo confirme.",
                )
                return redirect("liquidar_comision")
    nequi, titular = nequi_plataforma()
    return render(request, "vendedores/liquidar.html", {
        "vendedor": vendedor,
        "pendientes": pendientes,
        "reportadas": reportadas,
        "por_confirmar": por_confirmar,
        "deuda": deuda,
        "error": error,
        "nequi": nequi,
        "titular": titular,
        "llave": settings.PAGO_LLAVE,
        "bancolombia": settings.PAGO_BANCOLOMBIA,
    })


@login_required
@require_POST
def cancelar_pedido(request, pk):
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("registro_vendedor")
    pedido = get_object_or_404(Pedido, pk=pk, vendedor=vendedor)
    resultado = cancelar_pedido_vendedor(
        pedido, vendedor, acepta_sancion=request.POST.get("acepto") == "1",
    )
    if resultado == "anulado":
        messages.success(request, f"Pedido #{pedido.id} anulado. El cliente no había pagado, no hubo comisión.")
    elif resultado == "expulsado":
        messages.error(
            request,
            f"Pedido #{pedido.id} cancelado. La comisión ya estaba generada: la tienda salió de la página.",
        )
    elif resultado == "falta_aceptar":
        messages.error(
            request,
            "Esa venta ya tiene comisión. Para cancelarla debes aceptar que la tienda se retira de la página.",
        )
    elif resultado == "ya_liquidada":
        messages.error(request, "Esa comisión ya está liquidada. Si debes cancelar la venta, hazlo desde el administrador.")
    elif resultado == "giro_en_curso":
        messages.error(request, "El restante ya salió hacia el Nequi de la tienda. Este pedido no se puede anular aquí.")
    elif resultado == "giro_cancelado":
        messages.success(request, f"Pedido #{pedido.id} anulado. El dinero del vendedor todavía no había salido.")
    return redirect("panel_vendedor")


def tienda_publica(request, slug):
    from pedidos.services.visitas import registrar_visita
    vendedor = get_object_or_404(Vendedor, slug=slug, estado="activo")
    if "vendedor" in registrar_visita(request, vendedor_id=vendedor.id):
        vendedor.visitas += 1
    notas = vendedor.calificaciones.aggregate(promedio=Avg("estrellas"), total=Count("id"))
    productos = (
        vendedor.productos.filter(activo=True)
        .filter(Q(controla_stock=False) | Q(stock__gt=0))
        .select_related("rubro")
        .prefetch_related("fotos")
    )
    return render(request, "vendedores/tienda.html", {
        "tienda": vendedor,
        "productos": productos,
        "promedio": notas["promedio"],
        "total_calificaciones": notas["total"],
        "nota_publica": vendedor.calificacion_manual if vendedor.calificacion_manual is not None else notas["promedio"],
        "comentarios": vendedor.calificaciones.select_related("pedido").order_by("-creado")[:40],
    })


def estado_tienda(request, slug):
    vendedor = get_object_or_404(Vendedor, slug=slug, estado="activo")
    return render(request, "compartir/estado.html", {
        "modo": "tienda",
        "titulo": vendedor.nombre_tienda,
        "kicker": f"{vendedor.get_tipo_display()} · {vendedor.ciudad}",
        "precio": "",
        "detalle": "Entra a la tienda y pide. La conversación queda dentro del pedido.",
        "enlace": reverse("tienda_publica", args=[vendedor.slug]),
        "imagen": "",
    })
