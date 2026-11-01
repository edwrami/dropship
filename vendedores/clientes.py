from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import RegistroClienteForm
from .models import ClienteTienda, Conexion, Vendedor
from .opciones import DEPARTAMENTOS, TIPOS_PROVEEDOR


def _cliente(user):
    if not user.is_authenticated:
        return None
    try:
        return user.cliente_tienda
    except ClienteTienda.DoesNotExist:
        return None


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
            ciudad=data["ciudad"].strip(),
            departamento=data["departamento"],
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


@login_required(login_url="entrar_cliente")
def mis_proveedores(request):
    cliente = _cliente(request.user)
    if cliente is None:
        return redirect("registro_cliente")
    conexiones = cliente.conexiones.select_related("proveedor").order_by("proveedor__nombre_tienda")
    pedidos = cliente.pedidos.select_related("producto", "vendedor")
    return render(request, "clientes/mios.html", {
        "cliente": cliente,
        "conexiones": conexiones,
        "pedidos": pedidos,
    })
