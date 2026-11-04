from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from pedidos.models import Pedido

from .forms import DatosCompradorForm, RegistroClienteForm, RegistroCompradorForm
from .models import ClienteTienda, Comprador, Conexion, Vendedor
from .opciones import DEPARTAMENTOS, TIPOS_PROVEEDOR


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
        return redirect("mis_proveedores")
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
        messages.success(request, "Tienda registrada. Ya puedes conectarte con mayoristas e importadores.")
        return redirect("proveedores_mayor")
    return render(request, "clientes/registro.html", {"form": form})


def entrar_cliente(request):
    if _cliente(request.user):
        return redirect("mis_proveedores")
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
                error = "Esa cuenta es de vendedor. Entra desde Vender."
            else:
                return redirect("mis_proveedores")
    return render(request, "clientes/entrar.html", {"error": error})


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


@login_required(login_url="entrar_cliente")
def lista_mayorista(request, slug):
    cliente = _cliente(request.user)
    if cliente is None:
        messages.error(request, "Esta lista es para tiendas registradas.")
        return redirect("registro_cliente")
    proveedor = get_object_or_404(Vendedor, slug=slug, estado="activo", tipo__in=TIPOS_PROVEEDOR)
    if _conexion(cliente, proveedor) is None:
        messages.error(request, "Conéctate con este proveedor para ver sus precios al por mayor.")
        return redirect("proveedores_mayor")
    productos = (
        proveedor.productos.filter(activo=True, precio_mayor_cop__isnull=False)
        .filter(Q(controla_stock=False) | Q(stock__gt=0))
        .select_related("rubro", "rubro__padre")
        .prefetch_related("fotos")
    )
    return render(request, "clientes/lista.html", {
        "proveedor": proveedor,
        "productos": productos,
        "cliente": cliente,
    })


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
    return Pedido.objects.filter(consulta).select_related("producto", "vendedor")


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
    if request.method == "POST":
        cliente.direccion = (request.POST.get("direccion") or "").strip()
        cliente.barrio = (request.POST.get("barrio") or "").strip()[:120]
        cliente.referencia = (request.POST.get("referencia") or "").strip()[:200]
        if not cliente.direccion:
            messages.error(request, "Escribe la dirección de entrega.")
        else:
            cliente.save(update_fields=["direccion", "barrio", "referencia"])
            messages.success(request, "Dirección guardada.")
        return redirect("mis_proveedores")
    conexiones = cliente.conexiones.select_related("proveedor").order_by("proveedor__nombre_tienda")
    return render(request, "clientes/mios.html", {
        "cliente": cliente,
        "conexiones": conexiones,
        "pedidos": pedidos_del_comprador(request, cliente),
    })
