from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from pedidos.models import CuentaPlataforma, Giro, RetiroPlataforma
from pedidos.services.giros import autorizar_giro_venta, retirar_a_mi_nequi, saldo_era_en_wompi
from servicios.models import GiroCita
from servicios.pagos import autorizar_giro_cita


def _staff(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path(), login_url="/admin/login/")
    return None


def contexto_tesoreria():
    cuenta = CuentaPlataforma.objects.order_by("id").first()
    return {
        "saldo_era": saldo_era_en_wompi(),
        "cuenta_era": cuenta,
        "nequi_era": (cuenta.nequi if cuenta else "") or "",
        "payouts_listos": bool(cuenta and cuenta.payouts_api_key and cuenta.payouts_user_id),
        "retiros": RetiroPlataforma.objects.all()[:20],
    }


def panel(request):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    if request.method == "POST":
        return _post(request)
    ctx = contexto_tesoreria()
    ctx["giros_venta"] = (
        Giro.objects.exclude(estado__in=("pagado", "enviado"))
        .select_related("pedido", "pedido__vendedor")
        .order_by("-creado")[:80]
    )
    ctx["giros_oficio"] = (
        GiroCita.objects.exclude(estado__in=("pagado", "enviado"))
        .select_related("cita", "cita__oferente")
        .order_by("-creado")[:80]
    )
    return render(request, "pedidos/tesoreria.html", ctx)


def _post(request):
    accion = request.POST.get("accion")
    if accion == "retirar_nequi":
        retiro, error = retirar_a_mi_nequi(request.POST.get("monto") or 0)
        if error:
            messages.error(request, error)
        elif retiro and retiro.estado in ("enviado", "pagado"):
            messages.success(
                request,
                f"Wompi está enviando ${retiro.monto_cop} a tu Nequi {retiro.destino_nequi}.",
            )
        elif retiro:
            messages.error(request, retiro.detalle or "El retiro quedó en Wompi, sin salir todavía.")
    elif accion == "autorizar_venta":
        giro = get_object_or_404(Giro, pk=request.POST.get("giro") or 0)
        giro = autorizar_giro_venta(giro)
        messages.success(request, f"Giro pedido #{giro.pedido_id}: {giro.get_estado_display()}. {giro.detalle}")
    elif accion == "autorizar_oficio":
        giro = get_object_or_404(GiroCita, pk=request.POST.get("giro") or 0)
        giro = autorizar_giro_cita(giro.cita)
        if giro:
            messages.success(request, f"Giro cita #{giro.cita_id}: {giro.get_estado_display()}. {giro.detalle}")
        else:
            messages.error(request, "Esa cita aún no está lista para girar.")
    destino = request.POST.get("next") or "/pedidos/tesoreria/"
    if not destino.startswith("/") or destino.startswith("//"):
        destino = "/pedidos/tesoreria/"
    return redirect(destino)


@require_POST
def post_tesoreria(request):
    bloqueo = _staff(request)
    if bloqueo:
        return bloqueo
    return _post(request)
