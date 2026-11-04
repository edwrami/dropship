import csv
import uuid
from decimal import Decimal, InvalidOperation
from io import StringIO

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from pedidos.models import LineaPedido, Pedido
from productos.models import FotoProducto, Producto
from productos.services.storage import borrar_foto, extension, subir_foto

from .forms import DatosVendedorForm, ProductoVendedorForm, RegistroForm
from .opciones import DEPARTAMENTOS, TIPOS, TIPOS_PROVEEDOR
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


def _destino_registro(request):
    destino = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if destino in ("/vendedores/producto/nuevo/", "/vendedores/panel/"):
        return destino
    return "/vendedores/panel/"


@transaction.atomic
def registro(request):
    if _vendedor(request.user):
        return redirect(_destino_registro(request))
    inicial = {}
    if request.method == "GET":
        tipo = (request.GET.get("tipo") or "").strip()
        if tipo in dict(TIPOS):
            inicial["tipo"] = tipo
    form = RegistroForm(request.POST or None, initial=inicial)
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
            messages.success(request, "Registro listo. Ahora completa el producto si vas a publicarlo.")
            return redirect(_destino_registro(request))
    return render(request, "vendedores/registro.html", {
        "form": form,
        "grupos": _grupos(),
        "seleccionadas": seleccionadas,
        "next": _destino_registro(request) if request.GET.get("next") or request.POST.get("next") else "",
        "modo": (request.POST.get("modo") or request.GET.get("tipo") or "").strip(),
        "otra_cuenta": request.user.is_authenticated,
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
    pedidos = vendedor.pedidos.select_related("producto", "giro").prefetch_related("lineas").all()
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
    aprobados = pedidos.filter(estado_pago="aprobado")
    unidades_lineas = LineaPedido.objects.filter(
        pedido__vendedor=vendedor, pedido__estado_pago="aprobado",
    ).aggregate(s=Sum("cantidad"))["s"] or 0
    unidades_simples = aprobados.filter(lineas__isnull=True).aggregate(s=Sum("cantidad"))["s"] or 0
    pagado_neto = aprobados.filter(giro__estado="pagado").aggregate(s=Sum("neto_vendedor"))["s"] or 0
    pendiente_neto = aprobados.filter(
        Q(giro__isnull=True) | ~Q(giro__estado="pagado"),
    ).aggregate(s=Sum("neto_vendedor"))["s"] or 0
    bajos = productos.filter(activo=True, controla_stock=True, stock__lte=5)
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
        "unidades_vendidas": unidades_lineas + unidades_simples,
        "pagado_neto": pagado_neto,
        "pendiente_neto": pendiente_neto,
        "bajos": bajos,
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
        "frase": vendedor.frase,
        "horario": vendedor.horario,
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
            for campo in ("telefono", "whatsapp", "nequi", "direccion", "ciudad", "departamento", "tipo", "frase", "horario"):
                setattr(vendedor, campo, data[campo].strip() if isinstance(data[campo], str) else data[campo])
            logo = request.FILES.get("logo")
            if logo is not None:
                try:
                    ext, tipo_logo = extension(logo)
                    logo.seek(0)
                    ruta = f"logos/{vendedor.id}/{uuid.uuid4().hex[:12]}.{ext}"
                    url_logo = subir_foto(logo.read(), ruta, tipo_logo)
                    anterior = vendedor.logo_ruta
                    vendedor.logo_url = url_logo
                    vendedor.logo_ruta = ruta
                    if anterior and anterior != ruta:
                        borrar_foto(anterior)
                except (ValueError, RuntimeError) as exc:
                    messages.error(request, str(exc))
                    return render(request, "vendedores/datos.html", {
                        "form": form,
                        "grupos": _grupos(),
                        "seleccionadas": seleccionadas,
                        "vendedor": vendedor,
                    })
            vendedor.save()
            vendedor.categorias.set(categorias)
            from pedidos.services.giros import reintentar_pendientes
            reintentar_pendientes(vendedor)
            messages.success(request, "Datos de la tienda actualizados.")
            return redirect("panel_vendedor")
    return render(request, "vendedores/datos.html", {
        "form": form,
        "grupos": _grupos(),
        "seleccionadas": seleccionadas,
        "vendedor": vendedor,
    })


def publicar_producto(request):
    vendedor = _vendedor(request.user)
    if vendedor and vendedor.estado == "activo":
        return redirect("nuevo_producto")
    if vendedor:
        messages.error(request, "Tu tienda fue retirada y no puede publicar.")
        return redirect("panel_vendedor")
    if request.user.is_authenticated:
        return render(request, "vendedores/otra_cuenta.html", {"para": "publicar"})
    return redirect("/vendedores/registro/?next=/vendedores/producto/nuevo/")


def vender_mayor(request):
    vendedor = _vendedor(request.user)
    if vendedor and vendedor.es_proveedor:
        return redirect("panel_vendedor")
    if vendedor:
        return render(request, "vendedores/vender_mayor.html", {"vendedor": vendedor})
    if request.user.is_authenticated:
        return render(request, "vendedores/otra_cuenta.html", {"para": "mayor"})
    return redirect("/vendedores/registro/?tipo=mayorista&next=/vendedores/panel/")


@login_required(login_url="registro_vendedor")
def producto_form(request, pk=None):
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("/vendedores/registro/?next=/vendedores/producto/nuevo/")
    if vendedor.estado != "activo":
        messages.error(request, "Tu tienda fue retirada y no puede publicar.")
        return redirect("panel_vendedor")
    instancia = None
    if pk:
        instancia = get_object_or_404(Producto, pk=pk, vendedor=vendedor)
    form = ProductoVendedorForm(
        request.POST or None,
        instance=instancia,
        mayorista=vendedor.tipo in TIPOS_PROVEEDOR,
    )
    archivos = request.FILES.getlist("fotos") if request.method == "POST" else []
    if request.method == "POST" and form.is_valid():
        if len(archivos) > 3:
            form.add_error(None, "Puedes subir hasta 3 fotos por producto.")
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
        messages.success(request, "Producto publicado en la lista.")
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


def _digitos(valor):
    return "".join(ch for ch in (valor or "") if ch.isdigit())


def _perfil_de(user, nombre):
    try:
        return getattr(user, nombre)
    except ObjectDoesNotExist:
        return None


def recuperar(request):
    if request.user.is_authenticated and (
        _vendedor(request.user) or _perfil_de(request.user, "comprador") or _perfil_de(request.user, "cliente_tienda")
    ):
        return redirect("panel_vendedor" if _vendedor(request.user) else "lista_productos")
    error = ""
    if request.method == "POST":
        intentos = int(request.session.get("recuperar_intentos") or 0)
        if intentos >= 8:
            error = "Demasiados intentos. Cierra esta página y vuelve a intentar más tarde."
        else:
            request.session["recuperar_intentos"] = intentos + 1
            email = (request.POST.get("email") or "").strip().lower()
            documento = _digitos(request.POST.get("documento"))
            clave = request.POST.get("password") or ""
            clave2 = request.POST.get("password2") or ""
            user = User.objects.filter(username=email).first()
            coincide = False
            if user is not None and len(documento) >= 5:
                for nombre in ("vendedor", "comprador", "cliente_tienda"):
                    perfil = _perfil_de(user, nombre)
                    if perfil is not None and _digitos(perfil.documento) == documento:
                        coincide = True
                        break
            if not coincide or len(clave) < 8 or clave != clave2:
                error = "No coincide el correo con la cédula o el NIT de esa cuenta, o la clave nueva no cumple: mínimo 8 caracteres y las dos iguales."
            else:
                user.set_password(clave)
                user.save(update_fields=["password"])
                request.session["recuperar_intentos"] = 0
                login(request, user)
                messages.success(request, "Clave actualizada.")
                if _vendedor(user):
                    return redirect("panel_vendedor")
                if _perfil_de(user, "comprador"):
                    return redirect("datos_comprador")
                return redirect("mis_proveedores")
    return render(request, "vendedores/recuperar.html", {"error": error})


def _numero_lista(valor):
    texto = (valor or "").strip().replace("$", "").replace(" ", "")
    if not texto:
        return None
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _departamento_lista(valor):
    buscado = (valor or "").strip().casefold()
    for nombre in DEPARTAMENTOS:
        if nombre.casefold() == buscado:
            return nombre
    return ""


def _filas_lista(archivo):
    raw = archivo.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    texto = raw.decode("utf-8")
    muestra = texto[:2000]
    delim = ";" if muestra.count(";") >= muestra.count(",") else ","
    lector = csv.DictReader(StringIO(texto), delimiter=delim)
    filas = []
    for fila in lector:
        limpia = {}
        for clave, valor in (fila or {}).items():
            if not clave:
                continue
            limpia[clave.strip().lower()] = (valor or "").strip()
        if any(limpia.values()):
            filas.append(limpia)
    return filas


def _producto_desde_fila(vendedor, fila, rubros):
    nombre = (fila.get("nombre") or "")[:400]
    descripcion = fila.get("descripcion") or ""
    categoria = rubros.get((fila.get("categoria") or "").casefold())
    precio = _numero_lista(fila.get("precio"))
    mayor = _numero_lista(fila.get("precio_mayor"))
    try:
        minima = int((fila.get("cantidad_minima") or "").strip())
    except ValueError:
        minima = 0
    ciudad = (fila.get("ciudad") or "")[:100]
    departamento = _departamento_lista(fila.get("departamento"))
    try:
        entrega_min = int((fila.get("entrega_min") or "").strip())
        entrega_max = int((fila.get("entrega_max") or "").strip())
    except ValueError:
        entrega_min = entrega_max = None
    envio = (fila.get("envio") or "incluido").strip().lower()
    if envio not in ("incluido", "aparte", "contraentrega"):
        envio = ""
    costo = _numero_lista(fila.get("costo_envio")) or Decimal("0")
    stock_texto = (fila.get("stock") or "").strip()
    errores = []
    if len(nombre) < 3:
        errores.append("falta el nombre")
    if len(descripcion) < 80:
        errores.append("la descripción necesita al menos 80 caracteres")
    if categoria is None:
        errores.append("la categoría no existe")
    if precio is None or precio <= 0:
        errores.append("falta el precio")
    if mayor is None or mayor <= 0:
        errores.append("falta el precio al por mayor")
    if minima < 1:
        errores.append("la cantidad mínima es al menos 1")
    if not ciudad:
        errores.append("falta la ciudad")
    if not departamento:
        errores.append("el departamento no coincide")
    if entrega_min is None or entrega_max is None or entrega_max < entrega_min or entrega_min < 0:
        errores.append("revisa los días de entrega")
    if not envio:
        errores.append("el envío debe ser incluido, aparte o contraentrega")
    if envio == "aparte" and costo <= 0:
        errores.append("falta el costo de envío")
    stock = None
    if stock_texto:
        try:
            stock = int(stock_texto)
        except ValueError:
            stock = -1
        if stock < 0:
            errores.append("el stock no es un número")
    if errores:
        return None, ", ".join(errores)
    return {
        "titulo": nombre,
        "descripcion": descripcion,
        "rubro": categoria,
        "precio_final_cop": precio,
        "precio_mayor_cop": mayor,
        "cantidad_minima": minima,
        "ciudad_despacho": ciudad,
        "departamento_despacho": departamento,
        "tiempo_entrega_min": entrega_min,
        "tiempo_entrega_max": entrega_max,
        "modo_envio": envio,
        "costo_envio_cop": costo if envio == "aparte" else Decimal("0"),
        "envio_gratis": envio == "incluido",
        "stock": stock,
        "marca": (fila.get("marca") or "")[:120],
        "color": (fila.get("color") or "")[:80],
        "talla": (fila.get("talla") or "")[:40],
        "sku": (fila.get("sku") or "")[:80],
        "unidad_empaque": (fila.get("unidad_empaque") or "")[:80],
    }, ""


@login_required(login_url="registro_vendedor")
def cargar_lista(request):
    vendedor = _vendedor(request.user)
    if vendedor is None:
        return redirect("/vendedores/registro/?tipo=mayorista&next=/vendedores/panel/")
    if not vendedor.es_proveedor:
        return render(request, "vendedores/cargar_lista.html", {"vendedor": vendedor, "puede": False})
    if request.GET.get("ejemplo") == "1":
        ejemplo = (
            "nombre;descripcion;categoria;precio;precio_mayor;cantidad_minima;stock;ciudad;departamento;"
            "entrega_min;entrega_max;envio;costo_envio;marca;unidad_empaque\n"
            "Caja de vasos;Vaso de vidrio templado, caja por doce unidades, para restaurante. "
            "Medidas y material van en este texto hasta completar la ficha.;Vasos;24000;18000;12;;Medellín;Antioquia;2;5;incluido;0;Genérica;caja x 12\n"
        )
        respuesta = HttpResponse(ejemplo, content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = 'attachment; filename="lista-era-shop.csv"'
        return respuesta
    errores = []
    creados = 0
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if archivo is None:
            errores.append("Elige el archivo CSV.")
        elif archivo.size > 2 * 1024 * 1024:
            errores.append("El archivo puede pesar hasta 2 MB.")
        else:
            try:
                filas = _filas_lista(archivo)
            except UnicodeDecodeError:
                filas = []
                errores.append("Guarda el archivo como CSV en UTF-8.")
            if not errores and not filas:
                errores.append("El archivo no tiene filas.")
            elif not errores and len(filas) > 200:
                errores.append("Carga hasta 200 productos por archivo.")
            elif not errores:
                rubros = {
                    c.nombre.casefold(): c
                    for c in Categoria.objects.filter(padre__isnull=False)
                }
                listos = []
                for i, fila in enumerate(filas, start=2):
                    datos, fallo = _producto_desde_fila(vendedor, fila, rubros)
                    if fallo:
                        errores.append(f"Fila {i}: {fallo}.")
                    else:
                        listos.append(datos)
                for datos in listos:
                    stock = datos.pop("stock")
                    Producto.objects.create(
                        vendedor=vendedor,
                        origen="vendedor",
                        id_externo=f"vend-{vendedor.id}-{uuid.uuid4().hex[:16]}",
                        url_origen="",
                        tienda=vendedor.nombre_tienda,
                        moneda="COP",
                        margen_pct=0,
                        precio_costo=0,
                        activo=True,
                        controla_stock=stock is not None,
                        stock=stock or 0,
                        **datos,
                    )
                    creados += 1
                if creados:
                    reclasificar_vendedor(vendedor)
                    messages.success(request, f"Quedaron publicados {creados} productos.")
                if not errores and creados:
                    return redirect("panel_vendedor")
    return render(request, "vendedores/cargar_lista.html", {
        "vendedor": vendedor,
        "puede": True,
        "errores": errores,
        "creados": creados,
        "categorias": Categoria.objects.filter(padre__isnull=False).select_related("padre").order_by("padre__orden", "orden"),
    })


def estado_tienda(request, slug):
    vendedor = get_object_or_404(Vendedor, slug=slug, estado="activo")
    return render(request, "compartir/estado.html", {
        "modo": "tienda",
        "titulo": vendedor.nombre_tienda,
        "kicker": f"{vendedor.get_tipo_display()} · {vendedor.ciudad}",
        "precio": "",
        "detalle": vendedor.frase or "Entra a la tienda y pide. La conversación queda dentro del pedido.",
        "enlace": reverse("tienda_publica", args=[vendedor.slug]),
        "imagen": vendedor.logo_url,
    })
