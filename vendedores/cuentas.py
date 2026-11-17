from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import RegistroClienteForm, RegistroCompradorForm, RegistroForm
from .models import ClienteTienda, Comprador, Vendedor
from .opciones import TIPOS_DETAL, TIPOS_MAYOR, TIPOS_PROVEEDOR


def _siguiente(request, por_defecto):
    destino = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return por_defecto


def _vendedor(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.vendedor
    except Vendedor.DoesNotExist:
        return None


def _comprador(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.comprador
    except Comprador.DoesNotExist:
        return None


def _cliente(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.cliente_tienda
    except ClienteTienda.DoesNotExist:
        return None


def _oferente(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        return user.oferente
    except Exception:
        return None


def abrir_cuenta(request, email, password, password2=""):
    """Una sola cuenta por correo. Si ya existe, la contraseña suma el rol nuevo."""
    if request.user.is_authenticated:
        return request.user, None
    email = (email or "").strip().lower()
    if not email:
        return None, "Escribe el correo."
    if User.objects.filter(username=email).exists():
        user = authenticate(request, username=email, password=password or "")
        if user is None:
            return None, "Ese correo ya tiene cuenta. Escribe esa contraseña para añadir este rol, sin crear otra."
        return user, None
    if not password or len(password) < 8:
        return None, "La contraseña debe tener al menos 8 caracteres."
    if password != (password2 or ""):
        return None, "Las contraseñas no coinciden."
    return User.objects.create_user(username=email, email=email, password=password), None


def asegurar_comprador(user, data):
    nombre = (data.get("nombre") or data.get("responsable") or data.get("nombre_tienda") or "").strip()
    defaults = {
        "nombre": nombre[:200] or user.username,
        "documento": (data.get("documento") or "")[:40],
        "telefono": data.get("telefono") or "",
        "direccion": (data.get("direccion") or "").strip() or "Por confirmar",
        "barrio": (data.get("barrio") or "").strip(),
        "ciudad": (data.get("ciudad") or "").strip() or "Colombia",
        "departamento": data.get("departamento") or "",
        "referencia": (data.get("referencia") or "").strip(),
    }
    obj, creado = Comprador.objects.get_or_create(user=user, defaults=defaults)
    return obj, creado


def asegurar_cliente(user, data):
    defaults = {
        "nombre_tienda": (data.get("nombre_tienda") or data.get("nombre") or "").strip()[:160],
        "responsable": (data.get("responsable") or data.get("nombre") or "").strip()[:200],
        "documento": (data.get("documento") or "")[:40],
        "telefono": data.get("telefono") or "",
        "direccion": (data.get("direccion") or "").strip(),
        "barrio": (data.get("barrio") or "").strip(),
        "ciudad": (data.get("ciudad") or "").strip(),
        "departamento": data.get("departamento") or "",
        "referencia": (data.get("referencia") or "").strip(),
    }
    obj, creado = ClienteTienda.objects.get_or_create(user=user, defaults=defaults)
    return obj, creado


def destino_despues_entrar(user, next_url=""):
    if next_url:
        return next_url
    return "mi_panel"


def inicio_registro(request):
    rol = (request.GET.get("rol") or request.POST.get("rol") or "").strip()
    if rol == "cliente":
        return registro_cliente(request)
    if rol == "detal":
        return registro_vendedor(request, modo="detal")
    if rol == "mayorista":
        return registro_vendedor(request, modo="mayorista")
    return render(request, "cuentas/registro.html", {
        "next": request.GET.get("next", ""),
        "logueado": request.user.is_authenticated,
    })


def entrar_cuenta(request):
    if request.user.is_authenticated and request.method != "POST":
        return redirect(destino_despues_entrar(request.user, _siguiente(request, "")))
    error = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        user = authenticate(request, username=email, password=request.POST.get("password") or "")
        if user is None:
            error = "Correo o contraseña incorrectos."
        else:
            login(request, user)
            return redirect(destino_despues_entrar(user, _siguiente(request, "")))
    return render(request, "cuentas/entrar.html", {
        "error": error,
        "next": request.POST.get("next") or request.GET.get("next", ""),
    })


@transaction.atomic
def registro_cliente(request):
    if _comprador(request.user) and _cliente(request.user) is None and request.method == "GET":
        messages.info(request, "Con esta cuenta ya compras al detal. Completa el establecimiento si también pides al por mayor.")
    form = RegistroCompradorForm(
        request.POST or None,
        usuario=request.user if request.user.is_authenticated else None,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user, error = abrir_cuenta(request, data["email"], data.get("password") or "", data.get("password2") or "")
        if error:
            form.add_error("password", error)
        else:
            asegurar_comprador(user, data)
            if data.get("compra_mayor"):
                data = {**data, "nombre_tienda": data.get("nombre_tienda") or data["nombre"], "responsable": data["nombre"]}
                asegurar_cliente(user, data)
            login(request, user)
            messages.success(request, "Listo. Con el mismo correo puedes vender después, sin otra cuenta.")
            return redirect(_siguiente(request, "/clientes/cuenta/"))
    return render(request, "cuentas/form_cliente.html", {
        "form": form,
        "rol": "cliente",
        "next": request.GET.get("next") or request.POST.get("next", ""),
        "logueado": request.user.is_authenticated,
    })


@transaction.atomic
def registro_establecimiento(request):
    form = RegistroClienteForm(
        request.POST or None,
        usuario=request.user if request.user.is_authenticated else None,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user, error = abrir_cuenta(request, data["email"], data.get("password") or "", data.get("password2") or "")
        if error:
            form.add_error("password", error)
        elif _cliente(user):
            login(request, user)
            messages.info(request, "Este correo ya compra al por mayor.")
            return redirect(_siguiente(request, "/clientes/mis-proveedores/"))
        else:
            asegurar_cliente(user, data)
            asegurar_comprador(user, {
                **data,
                "nombre": data["responsable"],
            })
            login(request, user)
            messages.success(request, "Establecimiento listo. El mismo correo sirve para comprar al detal y, si quieres, para vender.")
            return redirect(_siguiente(request, "/clientes/proveedores/"))
    return render(request, "cuentas/form_establecimiento.html", {
        "form": form,
        "next": request.GET.get("next") or request.POST.get("next", ""),
        "logueado": request.user.is_authenticated,
    })


def _ids_categorias(request):
    return [int(x) for x in request.POST.getlist("categorias") if str(x).isdigit()]


@transaction.atomic
def registro_vendedor(request, modo="detal"):
    modo = (request.POST.get("rol") or request.GET.get("rol") or request.GET.get("tipo") or modo or "detal").strip()
    if modo in ("mayorista", "fabricante", "importador", "distribuidor"):
        modo = "mayorista"
    else:
        modo = "detal"
    vendedor = _vendedor(request.user)
    if vendedor:
        if modo == "mayorista" and vendedor.tipo not in TIPOS_PROVEEDOR:
            return render(request, "vendedores/vender_mayor.html", {"vendedor": vendedor})
        return redirect(_siguiente(request, "/vendedores/panel/"))
    inicial = {}
    if request.method == "GET" and modo == "mayorista":
        inicial["tipo"] = "mayorista"
    form = RegistroForm(
        request.POST or None,
        initial=inicial,
        usuario=request.user if request.user.is_authenticated else None,
        modo=modo,
    )
    from .models import Categoria
    seleccionadas = _ids_categorias(request) if request.method == "POST" else []
    if request.method == "POST" and form.is_valid():
        categorias = list(Categoria.objects.filter(pk__in=seleccionadas, padre__isnull=False))
        if not categorias:
            form.add_error(None, "Elige al menos una categoría de mercancía.")
        else:
            data = form.cleaned_data
            user, error = abrir_cuenta(request, data["email"], data.get("password") or "", data.get("password2") or "")
            if error:
                form.add_error("password", error)
            elif _vendedor(user):
                login(request, user)
                messages.info(request, "Este correo ya tiene tienda.")
                return redirect("panel_vendedor")
            else:
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
                asegurar_comprador(user, {
                    **data,
                    "nombre": data["responsable"],
                })
                login(request, user)
                messages.success(
                    request,
                    "Tienda lista. Con el mismo correo también puedes comprar. Marque el punto del mapa en sus datos: ERA shop calcula el flete y las partes no se conocen.",
                )
                return redirect(_siguiente(request, "/vendedores/panel/"))
    grupos = Categoria.objects.filter(padre__isnull=True).prefetch_related("hijos")
    return render(request, "cuentas/form_vendedor.html", {
        "form": form,
        "grupos": grupos,
        "seleccionadas": seleccionadas,
        "rol": modo,
        "next": request.GET.get("next") or request.POST.get("next", ""),
        "logueado": request.user.is_authenticated,
    })
