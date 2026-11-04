import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.http import Http404

from pedidos.models import Compra, LineaPedido, MensajePedido, Pedido
from productos.models import Producto

from .forms import DatosClienteForm, DatosCompradorForm, RegistroClienteForm, RegistroCompradorForm
from .models import (
    Carrito, CarritoComprador, CarritoCompradorLinea, CarritoLinea,
    ClienteTienda, Comprador, Conexion, Vendedor,
)
from .opciones import DEPARTAMENTOS, TIPOS_PROVEEDOR
from .services import aplicar_comision, cargos_mostrador_grupo, iva_mercancia, peso


def _cliente(user):
    if not user.is_authenticated:
        return None
    try:
        return user.cliente_tienda
    except ClienteTienda.DoesNotExist:
        return None


def _comprador(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.comprador
    except Comprador.DoesNotExist:
        return None


def _siguiente(request, por_defecto):
    destino = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return por_defecto


def _proveedores():
    return (
        Vendedor.objects.filter(estado="activo", tipo__in=TIPOS_PROVEEDOR)
        .prefetch_related("categorias")
        .order_by("ciudad", "nombre_tienda")
    )


@transaction.atomic
def registro_cliente(request):
    if _cliente(request.user):
        return redirect(_siguiente(request, "/clientes/mis-proveedores/"))
    form = RegistroClienteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = User.objects.create_user(
            username=data["email"],
            email=data["email"],
            password=data["password"],
        )
        ClienteTienda.objects.create(
            user=user,
            nombre_tienda=data["nombre_tienda"].strip(),
            responsable=data["responsable"].strip(),
            documento=data["documento"].strip(),
            telefono=data["telefono"],
            direccion=data["direccion"].strip(),
            barrio=(data.get("barrio") or "").strip(),
            ciudad=data["ciudad"].strip(),
            departamento=data["departamento"],
            referencia=(data.get("referencia") or "").strip(),
        )
        login(request, user)
        messages.success(request, "Establecimiento registrado. Esos datos quedan en ERA shop y se copian en cada pedido.")
        return redirect(_siguiente(request, "/clientes/proveedores/"))
    return render(request, "clientes/registro.html", {
        "form": form,
        "next": request.GET.get("next", ""),
    })


def entrar_cliente(request):
    if _cliente(request.user):
        return redirect(_siguiente(request, "/clientes/mis-proveedores/"))
    error = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password") or "")
        if user is None:
            error = "Correo o contraseña incorrectos."
        else:
            login(request, user)
            if _cliente(user) is None:
                logout(request)
                error = "Esa cuenta no es de un establecimiento. Entra por Registrarme o por Vender."
            else:
                return redirect(_siguiente(request, "/clientes/mis-proveedores/"))
    return render(request, "clientes/entrar.html", {
        "error": error,
        "next": request.POST.get("next") or request.GET.get("next", ""),
    })


def proveedores_mayor(request):
    qs = _proveedores()
    tipo = request.GET.get("tipo") or ""
    ciudad = (request.GET.get("ciudad") or "").strip()
    if tipo in TIPOS_PROVEEDOR:
        qs = qs.filter(tipo=tipo)
    if ciudad:
        qs = qs.filter(ciudad__icontains=ciudad)
    cliente = _cliente(request.user)
    conectados = set()
    if cliente:
        conectados = set(
            Conexion.objects.filter(cliente=cliente).values_list("proveedor_id", flat=True)
        )
    return render(request, "clientes/proveedores.html", {
        "proveedores": qs,
        "conectados": conectados,
        "cliente": cliente,
        "departamentos": DEPARTAMENTOS,
        "ciudad": ciudad,
        "tipo": tipo,
    })


@login_required(login_url="entrar_cliente")
@require_POST
def conectar_proveedor(request, slug):
    cliente = _cliente(request.user)
    if cliente is None:
        messages.error(request, "Entra con la cuenta de tu tienda para conectarte.")
        return redirect("entrar_cliente")
    proveedor = get_object_or_404(Vendedor, slug=slug, estado="activo", tipo__in=TIPOS_PROVEEDOR)
    Conexion.objects.get_or_create(cliente=cliente, proveedor=proveedor)
    messages.success(request, f"Conectado con {proveedor.nombre_tienda}. Ya ves su lista al por mayor.")
    return redirect("lista_mayorista", slug=proveedor.slug)


@login_required(login_url="entrar_cliente")
@require_POST
def desconectar_proveedor(request, slug):
    cliente = _cliente(request.user)
    if cliente is None:
        return redirect("entrar_cliente")
    proveedor = get_object_or_404(Vendedor, slug=slug, tipo__in=TIPOS_PROVEEDOR)
    Conexion.objects.filter(cliente=cliente, proveedor=proveedor).delete()
    messages.success(request, f"Dejaste de ver la lista de {proveedor.nombre_tienda}.")
    return redirect("proveedores_mayor")


def _conexion(cliente, proveedor):
    if cliente is None:
        return None
    return Conexion.objects.filter(cliente=cliente, proveedor=proveedor).first()


def _entero(valor, minimo=0, maximo=999):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    if numero < minimo:
        return None
    if numero > maximo:
        return maximo
    return numero


def _exigir_conexion(request, slug):
    cliente = _cliente(request.user)
    if cliente is None:
        messages.error(request, "Entra con la cuenta del establecimiento.")
        return None, None, redirect("entrar_cliente")
    proveedor = get_object_or_404(Vendedor, slug=slug, estado="activo", tipo__in=TIPOS_PROVEEDOR)
    if _conexion(cliente, proveedor) is None:
        messages.error(request, "Conéctate con este proveedor para ver sus precios al por mayor.")
        return None, None, redirect("proveedores_mayor")
    return cliente, proveedor, None


def _productos_lista(proveedor):
    return (
        proveedor.productos.filter(activo=True, precio_mayor_cop__isnull=False)
        .filter(Q(controla_stock=False) | Q(stock__gt=0))
        .select_related("rubro", "rubro__padre")
        .prefetch_related("fotos")
    )


def _obtener_carrito(cliente, proveedor):
    carrito, _creado = Carrito.objects.get_or_create(cliente=cliente, proveedor=proveedor)
    return carrito


def _limpiar_carrito(carrito):
    for linea in list(carrito.lineas.select_related("producto")):
        producto = linea.producto
        if (
            not producto.activo
            or producto.precio_mayor_cop is None
            or producto.vendedor_id != carrito.proveedor_id
        ):
            linea.delete()


def _guardar_seleccion(carrito, productos, request):
    errores = []
    guardados = 0
    for producto in productos:
        raw = (request.POST.get(f"cantidad_{producto.id}") or "").strip()
        if raw in ("", "0"):
            CarritoLinea.objects.filter(carrito=carrito, producto=producto).delete()
            continue
        cantidad = _entero(raw, 1, 999)
        minimo = producto.cantidad_minima or 1
        if cantidad is None or cantidad < minimo:
            errores.append(f"El mínimo de {producto.titulo} es {minimo}.")
            continue
        if producto.controla_stock and producto.stock < cantidad:
            errores.append(f"De {producto.titulo} solo hay {producto.stock}.")
            continue
        linea, _creada = CarritoLinea.objects.get_or_create(
            carrito=carrito, producto=producto, defaults={"cantidad": cantidad},
        )
        linea.cantidad = cantidad
        linea.save(update_fields=["cantidad"])
        guardados += 1
    if errores:
        messages.error(request, " ".join(errores))
    elif guardados:
        messages.success(request, "Pedido actualizado. La suma queda guardada en tu cuenta.")
    else:
        messages.success(request, "El pedido de este proveedor quedó vacío.")


def _filas_carrito(carrito):
    filas = []
    bienes = Decimal("0")
    envio = Decimal("0")
    unidades = 0
    for linea in carrito.lineas.select_related("producto"):
        producto = linea.producto
        precio = Decimal(producto.precio_mayor_cop or 0)
        modo = producto.modo_envio or ("incluido" if producto.envio_gratis else "aparte")
        envio_linea = Decimal(producto.costo_envio_cop or 0) if modo == "aparte" else Decimal("0")
        subtotal = peso(precio * linea.cantidad)
        bienes += subtotal
        envio += envio_linea
        unidades += linea.cantidad
        filas.append({
            "linea": linea,
            "producto": producto,
            "precio": precio,
            "modo": modo,
            "envio": envio_linea,
            "subtotal": subtotal,
        })
    return filas, peso(bienes), peso(envio), unidades


@login_required(login_url="entrar_cliente")
def lista_mayorista(request, slug):
    cliente, proveedor, respuesta = _exigir_conexion(request, slug)
    if respuesta:
        return respuesta
    productos = list(_productos_lista(proveedor))
    carrito = _obtener_carrito(cliente, proveedor)
    if request.method == "POST":
        if not cliente.registro_completo():
            messages.error(request, "Completa el registro del establecimiento antes de armar el pedido.")
            return redirect("mis_proveedores")
        _guardar_seleccion(carrito, productos, request)
        return redirect("lista_mayorista", slug=slug)
    _limpiar_carrito(carrito)
    en_pedido = {linea.producto_id: linea.cantidad for linea in carrito.lineas.all()}
    bienes = Decimal("0")
    unidades = 0
    for producto in productos:
        producto.en_pedido = en_pedido.get(producto.id, 0)
        if producto.en_pedido:
            bienes += Decimal(producto.precio_mayor_cop or 0) * producto.en_pedido
            unidades += producto.en_pedido
    return render(request, "clientes/lista.html", {
        "proveedor": proveedor,
        "productos": productos,
        "cliente": cliente,
        "suma_bienes": peso(bienes),
        "suma_unidades": unidades,
        "suma_productos": sum(1 for producto in productos if producto.en_pedido),
    })


@login_required(login_url="entrar_cliente")
@require_POST
def agregar_carrito(request, slug):
    cliente, proveedor, respuesta = _exigir_conexion(request, slug)
    if respuesta:
        return respuesta
    if not cliente.registro_completo():
        messages.error(request, "Completa el registro del establecimiento antes de armar el pedido.")
        return redirect("mis_proveedores")
    producto = get_object_or_404(
        proveedor.productos.filter(activo=True, precio_mayor_cop__isnull=False),
        pk=request.POST.get("producto") or 0,
    )
    minimo = producto.cantidad_minima or 1
    cantidad = _entero(request.POST.get("cantidad"), minimo, 999)
    destino = redirect("carrito_pedido", slug=slug)
    if cantidad is None:
        messages.error(request, f"El mínimo de {producto.titulo} es {minimo}.")
        return destino
    carrito = _obtener_carrito(cliente, proveedor)
    linea = CarritoLinea.objects.filter(carrito=carrito, producto=producto).first()
    nueva = cantidad if linea is None else min(999, linea.cantidad + cantidad)
    if producto.controla_stock and producto.stock < nueva:
        messages.error(request, f"De {producto.titulo} solo hay {producto.stock}.")
        return destino
    if linea is None:
        CarritoLinea.objects.create(carrito=carrito, producto=producto, cantidad=nueva)
    else:
        linea.cantidad = nueva
        linea.save(update_fields=["cantidad"])
    messages.success(request, f"{producto.titulo} quedó en el pedido. La suma ya incluye esa cantidad.")
    return destino


@login_required(login_url="entrar_cliente")
def carrito_pedido(request, slug):
    cliente, proveedor, respuesta = _exigir_conexion(request, slug)
    if respuesta:
        return respuesta
    if not cliente.registro_completo():
        messages.error(request, "Completa el registro del establecimiento antes de pedir.")
        return redirect("mis_proveedores")
    carrito = _obtener_carrito(cliente, proveedor)
    _limpiar_carrito(carrito)
    if request.method == "POST":
        accion = request.POST.get("accion") or ""
        if accion.startswith("quitar-"):
            carrito.lineas.filter(pk=accion.split("-")[-1] or 0).delete()
            messages.success(request, "Producto quitado. La suma se actualizó.")
            return redirect("carrito_pedido", slug=slug)
        if accion == "confirmar":
            pedido, error = _confirmar_carrito(request, cliente, proveedor, carrito)
            if error:
                messages.error(request, error)
            else:
                from pedidos.avisos import avisar_pedido_nuevo
                from pedidos.views import _marcar_contacto

                _marcar_contacto(request, pedido)
                avisar_pedido_nuevo(
                    pedido,
                    request.build_absolute_uri(f"/pedidos/{pedido.id}/?clave={pedido.clave_contacto}"),
                    request.build_absolute_uri(f"/pedidos/{pedido.id}/"),
                )
                return redirect(f"/pedidos/pagar/{pedido.id}/?clave={pedido.clave_contacto}")
    filas, bienes, envio, unidades = _filas_carrito(carrito)
    pct_iva, iva = iva_mercancia(bienes, True)
    from .services import porcentajes_comision, total_con_cargos

    _detalle, mayor = porcentajes_comision()
    sin = total_con_cargos(bienes + envio, mayor)
    con = total_con_cargos(bienes + envio + iva, mayor)
    return render(request, "clientes/carrito.html", {
        "proveedor": proveedor,
        "cliente": cliente,
        "filas": filas,
        "bienes": bienes,
        "envio": envio,
        "unidades": unidades,
        "iva_pct": pct_iva,
        "iva_cop": iva,
        "total_sin": sin["total"],
        "comision_sin": sin["comision"],
        "wompi_sin": sin["tarifa"],
        "neto_sin": sin["neto"],
        "total_con": con["total"],
        "comision_con": con["comision"],
        "wompi_con": con["tarifa"],
        "neto_con": con["neto"],
    })


@transaction.atomic
def _confirmar_carrito(request, cliente, proveedor, carrito):
    lineas = list(carrito.lineas.select_related("producto").order_by("id"))
    if not lineas:
        return None, "El pedido está vacío."
    bloqueados = {
        producto.id: producto
        for producto in Producto.objects.select_for_update().filter(
            pk__in=sorted({linea.producto_id for linea in lineas}),
        )
    }
    errores = []
    preparados = []
    bienes = Decimal("0")
    envio_total = Decimal("0")
    unidades = 0
    for linea in lineas:
        producto = bloqueados.get(linea.producto_id)
        raw = request.POST.get(f"cantidad_{linea.id}")
        cantidad = _entero(raw, 1, 999) if raw not in (None, "") else linea.cantidad
        titulo = producto.titulo if producto is not None else "Producto"
        if producto is None or cantidad is None:
            errores.append(f"La cantidad de {titulo} no es válida.")
            continue
        minimo = producto.cantidad_minima or 1
        if cantidad < minimo:
            errores.append(f"El mínimo de {titulo} es {minimo}.")
            continue
        if not producto.activo or producto.precio_mayor_cop is None:
            errores.append(f"{titulo} ya no está en la lista.")
            continue
        if producto.controla_stock and producto.stock < cantidad:
            errores.append(f"De {titulo} solo hay {producto.stock}.")
            continue
        precio = Decimal(producto.precio_mayor_cop)
        modo = producto.modo_envio or ("incluido" if producto.envio_gratis else "aparte")
        envio_linea = Decimal(producto.costo_envio_cop or 0) if modo == "aparte" else Decimal("0")
        subtotal = peso(precio * cantidad)
        bienes += subtotal
        envio_total += envio_linea
        unidades += cantidad
        preparados.append((linea, producto, cantidad, precio, modo, envio_linea, subtotal))
    if errores or not preparados:
        return None, " ".join(errores) or "No hay productos para pedir."
    con_iva = request.POST.get("factura") == "con"
    iva_pct, iva = iva_mercancia(bienes, con_iva)
    base = peso(bienes + envio_total)
    modos = {item[4] for item in preparados}
    modo = modos.pop() if len(modos) == 1 else "mixto"
    primero = preparados[0][1]
    pedido = Pedido.objects.create(
        producto=primero,
        vendedor=proveedor,
        cliente_tienda=cliente,
        cantidad=unidades,
        cliente_nombre=cliente.nombre_tienda,
        cliente_telefono=cliente.telefono,
        cliente_email=cliente.user.email,
        cliente_direccion=cliente.direccion,
        cliente_barrio=cliente.barrio,
        cliente_ciudad=cliente.ciudad,
        cliente_departamento=cliente.departamento,
        cliente_documento=cliente.documento,
        cliente_referencia=cliente.referencia,
        modo_envio=modo,
        envio_cop=peso(envio_total),
        monto_cop=base + iva,
        subtotal_cop=base,
        es_mayor=True,
        factura_iva=con_iva,
        iva_pct=iva_pct,
        iva_cop=iva,
        estado="pendiente",
        estado_pago="pendiente",
        contacto_responsable=proveedor.responsable,
        contacto_telefono=proveedor.telefono,
        contacto_whatsapp=proveedor.whatsapp,
        contacto_email=proveedor.user.email,
        contacto_direccion=proveedor.direccion,
        contacto_nequi=proveedor.nequi,
        clave_contacto=uuid.uuid4().hex,
    )
    pedido.referencia_pago = f"PED-{pedido.id}"
    aplicar_comision(pedido)
    pedido.save()
    textos = []
    for linea, producto, cantidad, precio, modo_linea, envio_linea, subtotal in preparados:
        LineaPedido.objects.create(
            pedido=pedido,
            producto=producto,
            titulo=producto.titulo[:300],
            cantidad=cantidad,
            precio_unitario=precio,
            modo_envio=modo_linea,
            envio_cop=envio_linea,
            subtotal_cop=subtotal,
        )
        if producto.controla_stock:
            producto.stock -= cantidad
            producto.save(update_fields=["stock"])
        linea.delete()
        textos.append(f"{producto.titulo}: {cantidad} × ${peso(precio)}")
    factura = "Factura con IVA." if con_iva else "Factura sin IVA."
    MensajePedido.objects.create(
        pedido=pedido,
        autor="plataforma",
        nombre="ERA shop",
        texto=(
            f"Pedido al por mayor de {cliente.nombre_tienda}, responsable {cliente.responsable}. "
            f"{factura} Queda guardado para el establecimiento y para el proveedor.\n"
            + "\n".join(textos)
        ),
    )
    return pedido, ""


def pedidos_del_comprador(request, cliente=None, comprador=None):
    ids = []
    for valor in request.session.get("pedidos_contacto") or []:
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    if cliente is None and comprador is None and not ids:
        return Pedido.objects.none()
    consulta = Q(pk__in=ids) if ids else Q(pk__isnull=True)
    if cliente is not None:
        consulta |= Q(cliente_tienda=cliente)
        email = (cliente.user.email or "").strip()
        if email:
            consulta |= Q(cliente_email__iexact=email)
    if comprador is not None:
        consulta |= Q(comprador=comprador)
        email = (comprador.user.email or "").strip()
        if email:
            consulta |= Q(cliente_email__iexact=email)
    return (
        Pedido.objects.filter(consulta)
        .select_related("producto", "vendedor")
        .prefetch_related("lineas")
    )


def historial_comprador(request):
    cliente = _cliente(request.user)
    comprador = _comprador(request.user)
    if cliente is not None and comprador is None:
        return redirect("mis_proveedores")
    return render(request, "clientes/historial.html", {
        "pedidos": pedidos_del_comprador(request, cliente, comprador),
        "comprador": comprador,
    })


def registro_comprador(request):
    if _comprador(request.user):
        return redirect(_siguiente(request, "/clientes/cuenta/"))
    form = RegistroCompradorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = User.objects.create_user(
            username=data["email"],
            email=data["email"],
            password=data["password"],
        )
        Comprador.objects.create(
            user=user,
            nombre=data["nombre"].strip(),
            documento=data["documento"],
            telefono=data["telefono"],
            direccion=data["direccion"].strip(),
            barrio=(data.get("barrio") or "").strip(),
            ciudad=data["ciudad"].strip(),
            departamento=data["departamento"],
            referencia=(data.get("referencia") or "").strip(),
        )
        login(request, user)
        messages.success(request, "Registro guardado. Ya puedes hacer el pedido.")
        return redirect(_siguiente(request, "/clientes/cuenta/"))
    return render(request, "clientes/registro_comprador.html", {
        "form": form,
        "next": request.GET.get("next", ""),
    })


def entrar_comprador(request):
    if _comprador(request.user):
        return redirect(_siguiente(request, "/clientes/cuenta/"))
    error = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password") or "")
        if user is None:
            error = "Correo o contraseña incorrectos."
        else:
            login(request, user)
            if _comprador(user) is None:
                logout(request)
                error = "Esa cuenta no es de comprador. Una tienda entra por Soy tienda y un vendedor por Vender."
            else:
                return redirect(_siguiente(request, "/clientes/cuenta/"))
    return render(request, "clientes/entrar_comprador.html", {
        "error": error,
        "next": request.POST.get("next") or request.GET.get("next", ""),
    })


@login_required(login_url="entrar_comprador")
def datos_comprador(request):
    comprador = _comprador(request.user)
    if comprador is None:
        return redirect("registro_comprador")
    form = DatosCompradorForm(request.POST or None, instance=comprador)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Datos actualizados.")
        return redirect("datos_comprador")
    from productos.views import vitrina_comprador

    ctx = vitrina_comprador(request)
    ctx.update({
        "form": form,
        "comprador": comprador,
        "pedidos": pedidos_del_comprador(request, None, comprador),
    })
    return render(request, "clientes/cuenta.html", ctx)


@login_required(login_url="entrar_cliente")
def mis_proveedores(request):
    cliente = _cliente(request.user)
    if cliente is None:
        return redirect("registro_cliente")
    form = DatosClienteForm(request.POST or None, instance=cliente)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Datos del establecimiento actualizados.")
        return redirect("mis_proveedores")
    conexiones = cliente.conexiones.select_related("proveedor").order_by("proveedor__nombre_tienda")
    abiertos = []
    for carrito in cliente.carritos.select_related("proveedor").prefetch_related("lineas__producto"):
        lineas = [
            linea for linea in carrito.lineas.all()
            if linea.producto.activo and linea.producto.precio_mayor_cop is not None
        ]
        if not lineas:
            continue
        bienes = sum((Decimal(linea.producto.precio_mayor_cop) * linea.cantidad for linea in lineas), Decimal("0"))
        abiertos.append({
            "proveedor": carrito.proveedor,
            "productos": len(lineas),
            "unidades": sum(linea.cantidad for linea in lineas),
            "bienes": peso(bienes),
        })
    return render(request, "clientes/mios.html", {
        "cliente": cliente,
        "form": form,
        "conexiones": conexiones,
        "pedidos": pedidos_del_comprador(request, cliente),
        "abiertos": abiertos,
    })


def _carrito_de(comprador):
    carrito, _creado = CarritoComprador.objects.get_or_create(comprador=comprador)
    return carrito


def _preparar_linea(producto, cantidad):
    precio = Decimal(producto.precio_vigente)
    modo = producto.modo_envio or ("incluido" if producto.envio_gratis else "aparte")
    envio = Decimal(producto.costo_envio_cop or 0) if modo == "aparte" else Decimal("0")
    return {
        "producto": producto,
        "cantidad": cantidad,
        "precio": precio,
        "modo": modo,
        "envio": envio,
        "subtotal": peso(precio * cantidad + envio),
    }


def _grupos_carrito(lineas):
    grupos = []
    indice = {}
    total = Decimal("0")
    for linea in lineas:
        producto = linea.producto
        if not producto.activo or (producto.vendedor_id and producto.vendedor.estado != "activo"):
            continue
        item = _preparar_linea(producto, linea.cantidad)
        item["linea"] = linea
        clave = producto.vendedor_id or 0
        if clave not in indice:
            indice[clave] = {
                "tienda": producto.vendedor,
                "items": [],
                "suma": Decimal("0"),
            }
            grupos.append(indice[clave])
        indice[clave]["items"].append(item)
        indice[clave]["suma"] += item["subtotal"]
        total += item["subtotal"]
    for grupo in grupos:
        grupo["suma"] = peso(grupo["suma"])
    return grupos, peso(total)


@require_POST
def agregar_compra(request):
    try:
        producto_id = int(request.POST.get("producto") or 0)
    except (TypeError, ValueError):
        producto_id = 0
    producto = (
        Producto.objects.filter(pk=producto_id, activo=True)
        .select_related("vendedor")
        .first()
    )
    if producto is None or (producto.vendedor_id and producto.vendedor.estado != "activo"):
        messages.error(request, "Ese producto ya no está disponible.")
        return redirect("lista_productos")
    comprador = _comprador(request.user)
    if comprador is None:
        return redirect(f"/clientes/cuenta/registro/?next=/producto/{producto.pk}/")
    try:
        cantidad = int(request.POST.get("cantidad") or 1)
    except (TypeError, ValueError):
        cantidad = 1
    cantidad = max(1, min(cantidad, 20))
    carrito = _carrito_de(comprador)
    linea, creada = CarritoCompradorLinea.objects.get_or_create(
        carrito=carrito, producto=producto, defaults={"cantidad": cantidad},
    )
    if not creada:
        linea.cantidad = min(20, linea.cantidad + cantidad)
        linea.save(update_fields=["cantidad"])
    messages.success(request, "Quedó en el carrito. Puedes sumar más productos de esta tienda o de otras.")
    return redirect("carrito_compra")


@login_required(login_url="entrar_comprador")
def carrito_compra(request):
    comprador = _comprador(request.user)
    if comprador is None:
        return redirect("registro_comprador")
    carrito = _carrito_de(comprador)
    retirados = carrito.lineas.exclude(producto__activo=True).count()
    retirados += carrito.lineas.filter(producto__vendedor__estado="expulsado").count()
    if retirados:
        carrito.lineas.exclude(producto__activo=True).delete()
        carrito.lineas.filter(producto__vendedor__estado="expulsado").delete()
        messages.error(request, "Se quitaron productos que ya no están disponibles.")
    if request.method == "POST":
        accion = request.POST.get("accion") or ""
        if accion.startswith("quitar-"):
            try:
                linea_id = int(accion.split("-", 1)[1])
            except (TypeError, ValueError):
                linea_id = 0
            carrito.lineas.filter(pk=linea_id).delete()
            return redirect("carrito_compra")
        for linea in carrito.lineas.all():
            try:
                cantidad = int(request.POST.get(f"cantidad-{linea.id}") or linea.cantidad)
            except (TypeError, ValueError):
                cantidad = linea.cantidad
            linea.cantidad = max(1, min(cantidad, 20))
            linea.save(update_fields=["cantidad"])
        if accion == "pagar":
            compra, error = _cerrar_carrito(comprador, carrito)
            if error:
                messages.error(request, error)
                return redirect("carrito_compra")
            _avisar_compra(request, compra)
            return redirect(f"/clientes/carrito/pagar/{compra.id}/?clave={compra.clave_contacto}")
        messages.success(request, "Carrito actualizado.")
        return redirect("carrito_compra")
    lineas = list(
        carrito.lineas.select_related("producto__vendedor").order_by("producto__vendedor_id", "id")
    )
    grupos, total = _grupos_carrito(lineas)
    return render(request, "clientes/carrito_compra.html", {
        "grupos": grupos,
        "total": total,
        "comprador": comprador,
    })


def _cerrar_carrito(comprador, carrito):
    with transaction.atomic():
        carrito = CarritoComprador.objects.select_for_update().get(pk=carrito.pk)
        lineas = list(
            carrito.lineas.select_related("producto__vendedor__user").order_by("id")
        )
        if not lineas:
            return None, "El carrito está vacío."
        ids = sorted({linea.producto_id for linea in lineas})
        bloqueados = {
            producto.id: producto
            for producto in Producto.objects.select_for_update().filter(pk__in=ids).order_by("id")
        }
        grupos = {}
        orden = []
        for linea in lineas:
            producto = bloqueados.get(linea.producto_id)
            vendedor = linea.producto.vendedor
            if producto is None or not producto.activo or (vendedor and vendedor.estado != "activo"):
                return None, "Hay un producto que ya no está disponible. Quítalo del carrito."
            cantidad = max(1, min(linea.cantidad, 20))
            if producto.controla_stock and producto.stock < cantidad:
                return None, f"No hay suficientes unidades de {producto.titulo}."
            clave = vendedor.id if vendedor else 0
            if clave not in grupos:
                grupos[clave] = []
                orden.append(clave)
            item = _preparar_linea(producto, cantidad)
            item["vendedor"] = vendedor
            grupos[clave].append(item)
        compra = Compra.objects.create(
            comprador=comprador,
            referencia_pago=uuid.uuid4().hex,
            cliente_email=(comprador.user.email or "")[:254],
            clave_contacto=uuid.uuid4().hex,
            estado_pago="pendiente",
        )
        pedidos = []
        for clave in orden:
            items = grupos[clave]
            primero = items[0]["producto"]
            vendedor = items[0]["vendedor"]
            monto = peso(sum((item["subtotal"] for item in items), Decimal("0")))
            envio = peso(sum((item["envio"] for item in items), Decimal("0")))
            modos = {item["modo"] for item in items}
            pedido = Pedido.objects.create(
                producto=primero,
                vendedor=vendedor,
                comprador=comprador,
                compra=compra,
                cantidad=sum(item["cantidad"] for item in items),
                cliente_nombre=comprador.nombre,
                cliente_telefono=comprador.telefono,
                cliente_email=comprador.user.email or "",
                cliente_direccion=comprador.direccion,
                cliente_barrio=comprador.barrio,
                cliente_ciudad=comprador.ciudad,
                cliente_departamento=comprador.departamento,
                cliente_documento=comprador.documento,
                cliente_referencia=comprador.referencia,
                modo_envio=items[0]["modo"] if len(modos) == 1 else "",
                envio_cop=envio,
                monto_cop=monto,
                subtotal_cop=monto,
                es_mayor=False,
                estado="pendiente",
                estado_pago="pendiente",
                referencia_pago=uuid.uuid4().hex,
                contacto_responsable=vendedor.responsable if vendedor else "",
                contacto_telefono=vendedor.telefono if vendedor else "",
                contacto_whatsapp=vendedor.whatsapp if vendedor else "",
                contacto_email=vendedor.user.email if vendedor else "",
                contacto_direccion=vendedor.direccion if vendedor else "",
                contacto_nequi=vendedor.nequi if vendedor else "",
                clave_contacto=uuid.uuid4().hex,
            )
            pedido.referencia_pago = f"PED-{pedido.id}"
            if len(items) > 1:
                for item in items:
                    LineaPedido.objects.create(
                        pedido=pedido,
                        producto=item["producto"],
                        titulo=item["producto"].titulo[:300],
                        cantidad=item["cantidad"],
                        precio_unitario=item["precio"],
                        modo_envio=item["modo"],
                        envio_cop=item["envio"],
                        subtotal_cop=item["subtotal"],
                    )
            pedidos.append(pedido)
            for item in items:
                producto = item["producto"]
                if producto.controla_stock:
                    producto.stock -= item["cantidad"]
                    producto.save(update_fields=["stock"])
        cargos_mostrador_grupo(pedidos)
        for pedido in pedidos:
            pedido.save()
            MensajePedido.objects.create(
                pedido=pedido,
                autor="plataforma",
                nombre="ERA shop",
                texto=(
                    "Pedido creado desde el carrito. El teléfono, WhatsApp, correo y dirección "
                    "del vendedor aparecen cuando la transferencia quede aprobada."
                ),
            )
        compra.referencia_pago = f"COM-{compra.id}"
        compra.monto_cop = peso(sum((Decimal(str(p.monto_cop or 0)) for p in pedidos), Decimal("0")))
        compra.save()
        carrito.lineas.all().delete()
        return compra, ""


def _avisar_compra(request, compra):
    from pedidos.avisos import avisar_pedido_nuevo
    from pedidos.views import _marcar_contacto

    for pedido in compra.pedidos.select_related("producto", "vendedor"):
        _marcar_contacto(request, pedido)
        try:
            avisar_pedido_nuevo(
                pedido,
                request.build_absolute_uri(f"/pedidos/{pedido.id}/?clave={pedido.clave_contacto}"),
                request.build_absolute_uri(f"/pedidos/{pedido.id}/"),
            )
        except Exception:
            pass


def _compra_visible(request, compra):
    if request.user.is_authenticated and request.user.is_staff:
        return True
    comprador = _comprador(request.user)
    if comprador is not None and compra.comprador_id == comprador.id:
        return True
    clave = (request.GET.get("clave") or "").strip()
    return bool(clave and clave == compra.clave_contacto)


@login_required(login_url="entrar_comprador")
def pagar_compra(request, compra_id):
    compra = get_object_or_404(Compra.objects.prefetch_related("pedidos__producto", "pedidos__lineas"), pk=compra_id)
    if not _compra_visible(request, compra):
        raise Http404("Compra no disponible")
    pedidos = list(compra.pedidos.all())
    if compra.estado_pago == "aprobado" or (pedidos and all(p.estado_pago == "aprobado" for p in pedidos)):
        return redirect(f"/clientes/carrito/resultado/{compra.id}/?clave={compra.clave_contacto}")
    from pedidos.services import wompi

    wompi_ctx = None
    if wompi.checkout_listo():
        destino = request.build_absolute_uri(f"/clientes/carrito/resultado/{compra.id}/?clave={compra.clave_contacto}")
        wompi_ctx = wompi.contexto_widget(compra, destino)
    return render(request, "clientes/pagar_compra.html", {
        "compra": compra,
        "pedidos": pedidos,
        "wompi": wompi_ctx,
        "tarjeta_lista": wompi_ctx is not None,
    })


def resultado_compra(request, compra_id):
    compra = get_object_or_404(Compra, pk=compra_id)
    if not _compra_visible(request, compra):
        raise Http404("Compra no disponible")
    tx_id = (request.GET.get("id") or "").strip()[:80]
    if tx_id and compra.estado_pago != "aprobado":
        from pedidos.services import wompi
        from pedidos.views import _aplicar_transaccion

        publica = wompi.claves_wompi()[0]
        tx = wompi.consultar_transaccion(tx_id, publica)
        misma_ref = tx and (tx.get("reference") or "") == compra.referencia_pago
        mismo_valor = tx and int(tx.get("amount_in_cents") or 0) == wompi.monto_centavos(compra)
        if misma_ref and mismo_valor:
            for pedido in compra.pedidos.all():
                _aplicar_transaccion(pedido, tx)
            estado = (tx.get("status") or "").upper()
            if estado == "APPROVED":
                compra.estado_pago = "aprobado"
            elif estado in ("DECLINED", "VOIDED"):
                compra.estado_pago = "declinado"
            elif estado == "ERROR":
                compra.estado_pago = "error"
            else:
                compra.estado_pago = "reportado"
            compra.save(update_fields=["estado_pago"])
    pedidos = list(compra.pedidos.select_related("producto", "vendedor").prefetch_related("lineas"))
    return render(request, "clientes/resultado_compra.html", {
        "compra": compra,
        "pedidos": pedidos,
        "pagado": compra.estado_pago == "aprobado",
    })
