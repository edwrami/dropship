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

from pedidos.models import LineaPedido, MensajePedido, Pedido
from productos.models import Producto

from .forms import DatosClienteForm, DatosCompradorForm, RegistroClienteForm, RegistroCompradorForm
from .models import Carrito, CarritoLinea, ClienteTienda, Comprador, Conexion, Vendedor
from .opciones import DEPARTAMENTOS, TIPOS_PROVEEDOR
from .services import aplicar_comision, iva_mercancia, peso


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
    return render(request, "clientes/cuenta.html", {
        "form": form,
        "comprador": comprador,
        "pedidos": pedidos_del_comprador(request, None, comprador),
    })


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
