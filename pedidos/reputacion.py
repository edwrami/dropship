from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from productos.models import Producto
from vendedores.models import Vendedor

from .models import Calificacion, CuentaPlataforma


def _staff(request):
    return request.user.is_authenticated and request.user.is_staff


def _entero(valor):
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    if numero < 0 or numero > 2_000_000_000:
        return None
    return numero


def _nota(valor):
    texto = (valor or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        nota = Decimal(texto)
    except InvalidOperation:
        raise ValueError
    if nota < 0 or nota > 5:
        raise ValueError
    return nota.quantize(Decimal("0.1"))


def _aplicar(request):
    accion = request.POST.get("accion") or ""
    if accion == "sitio":
        visitas = _entero(request.POST.get("visitas"))
        if visitas is None:
            messages.error(request, "Las visitas de la página tienen que ser un número de cero en adelante.")
            return
        cuenta, _creada = CuentaPlataforma.objects.get_or_create(pk=1)
        cuenta.visitas = visitas
        cuenta.save(update_fields=["visitas"])
        messages.success(request, f"ERA shop queda con {visitas} visitas.")
        return
    if accion == "vendedor":
        vendedor = get_object_or_404(Vendedor, pk=request.POST.get("id") or 0)
        visitas = _entero(request.POST.get("visitas"))
        if visitas is None:
            messages.error(request, "Las visitas de la tienda tienen que ser un número de cero en adelante.")
            return
        try:
            nota = _nota(request.POST.get("nota"))
        except ValueError:
            messages.error(request, "La calificación va de 0 a 5. Déjala vacía para usar el promedio de los comentarios.")
            return
        vendedor.visitas = visitas
        vendedor.calificacion_manual = nota
        vendedor.save(update_fields=["visitas", "calificacion_manual"])
        messages.success(request, f"{vendedor.nombre_tienda}: visitas y calificación actualizadas.")
        return
    if accion == "producto":
        producto = get_object_or_404(Producto, pk=request.POST.get("id") or 0)
        visitas = _entero(request.POST.get("visitas"))
        if visitas is None:
            messages.error(request, "Las visitas del producto tienen que ser un número de cero en adelante.")
            return
        producto.visitas = visitas
        producto.save(update_fields=["visitas"])
        messages.success(request, f"{producto.titulo}: {visitas} visitas.")
        return
    if accion == "comentario":
        nota = get_object_or_404(Calificacion, pk=request.POST.get("id") or 0)
        try:
            estrellas = int(request.POST.get("estrellas") or 0)
        except ValueError:
            estrellas = 0
        if estrellas < 1 or estrellas > 5:
            messages.error(request, "Las estrellas del comentario van de 1 a 5.")
            return
        nota.estrellas = estrellas
        nota.comentario = (request.POST.get("comentario") or "").strip()[:500]
        nota.save(update_fields=["estrellas", "comentario"])
        messages.success(request, "Comentario actualizado.")
        return
    if accion == "borrar_comentario":
        nota = get_object_or_404(Calificacion, pk=request.POST.get("id") or 0)
        tienda = nota.vendedor.nombre_tienda
        nota.delete()
        messages.success(request, f"Comentario de {tienda} borrado.")
        return
    messages.error(request, "No reconozco esa acción.")


def reputacion(request):
    if not _staff(request):
        return redirect_to_login(request.get_full_path(), login_url="/admin/login/")
    if request.method == "POST":
        _aplicar(request)
        return redirect(request.get_full_path())
    q = (request.GET.get("q") or "").strip()
    cuenta, _creada = CuentaPlataforma.objects.get_or_create(pk=1)
    vendedores = Vendedor.objects.annotate(
        promedio=Avg("calificaciones__estrellas"),
        total_notas=Count("calificaciones"),
    ).order_by("nombre_tienda")
    productos = Producto.objects.select_related("vendedor").order_by("-visitas", "titulo")
    comentarios = Calificacion.objects.select_related("vendedor", "pedido").order_by("-creado")
    if q:
        vendedores = vendedores.filter(nombre_tienda__icontains=q)
        productos = productos.filter(Q(titulo__icontains=q) | Q(vendedor__nombre_tienda__icontains=q))
        comentarios = comentarios.filter(
            Q(comentario__icontains=q) | Q(vendedor__nombre_tienda__icontains=q) | Q(pedido__cliente_nombre__icontains=q)
        )
    return render(request, "pedidos/reputacion.html", {
        "q": q,
        "cuenta": cuenta,
        "vendedores": vendedores[:100],
        "productos": Paginator(productos, 25).get_page(request.GET.get("pagina")),
        "comentarios": comentarios[:80],
    })
