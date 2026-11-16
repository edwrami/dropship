from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.urls import reverse
from pedidos.models import Giro, Pedido
from pedidos.services import wompi
from servicios.models import Cita, Consulta, GiroCita, Oferente
from servicios.pagos import (
    abrir_cobro_inscripcion,
    abrir_cobro_mensual,
    cuota_activacion,
    cuota_mensualidad,
    cuota_primera,
)

from .clientes import _cliente, _comprador, pedidos_del_comprador
from .models import Vendedor


def _vendedor(user):
    try:
        return user.vendedor
    except Vendedor.DoesNotExist:
        return None


def _oferente(user):
    try:
        return user.oferente
    except Oferente.DoesNotExist:
        return None


@login_required(login_url="entrar_cuenta")
def mi_panel(request):
    user = request.user
    vendedor = _vendedor(user)
    comprador = _comprador(user)
    cliente = _cliente(user)
    oferente = _oferente(user)

    ventas = Pedido.objects.none()
    if vendedor:
        ventas = vendedor.pedidos.select_related("producto", "giro").prefetch_related("lineas")
    compras = Pedido.objects.none()
    if cliente or comprador:
        compras = pedidos_del_comprador(request, cliente, comprador)
    citas_contratadas = (
        Cita.objects.filter(cliente=user)
        .select_related("oferente", "especialidad", "giro", "comentario")
        .order_by("-inicio")
    )
    consultas_hechas = Consulta.objects.filter(cliente=user).select_related("oferente", "especialidad")[:40]
    citas_recibidas = Cita.objects.none()
    consultas_recibidas = Consulta.objects.none()
    if oferente:
        citas_recibidas = oferente.citas.select_related("especialidad", "giro", "pago").order_by("-inicio")
        consultas_recibidas = oferente.consultas.select_related("especialidad")[:40]
        abrir_cobro_mensual(oferente)

    giros_venta = Giro.objects.filter(pedido__vendedor=vendedor).select_related("pedido")[:80] if vendedor else Giro.objects.none()
    giros_oficio = GiroCita.objects.filter(cita__oferente=oferente).select_related("cita", "cita__oferente")[:80] if oferente else GiroCita.objects.none()

    despachos = ventas.filter(estado_pago="aprobado").exclude(estado__in=("pendiente", "fallido"))[:40] if vendedor else Pedido.objects.none()

    pagos_hechos = []
    compras = compras[:80]
    citas_contratadas = citas_contratadas[:80]
    for pedido in compras:
        pagos_hechos.append({
            "cuando": pedido.creado,
            "que": f"Pedido #{pedido.id}",
            "monto": pedido.monto_cop,
            "estado": pedido.get_estado_pago_display(),
            "url": reverse("conversacion_pedido", args=[pedido.id]) if pedido.pk else "",
        })
    for cita in citas_contratadas:
        pagos_hechos.append({
            "cuando": cita.creado,
            "que": f"Cita con {cita.oferente.nombre}",
            "monto": cita.monto_cop,
            "estado": cita.estado_pago,
            "url": f"{reverse('resultado_cita', args=[cita.id])}?clave={cita.clave_contacto}",
        })
    if oferente:
        act = getattr(oferente, "activacion", None)
        if act:
            pagos_hechos.append({
                "cuando": act.creado,
                "que": "Inscripción de oferente (incluye el primer mes)",
                "monto": act.monto_cop,
                "estado": act.estado_pago,
                "url": reverse("activar_oferente"),
            })
        for men in oferente.pagos_mensuales.order_by("-id")[:12]:
            pagos_hechos.append({
                "cuando": men.creado,
                "que": "Mensualidad de oferente",
                "monto": men.monto_cop,
                "estado": men.estado_pago,
                "url": reverse("mensualidad_oferente"),
            })
        for extra in oferente.pagos_extra.order_by("-id")[:12]:
            pagos_hechos.append({
                "cuando": extra.creado,
                "que": extra.get_tipo_display(),
                "monto": extra.monto_cop,
                "estado": extra.estado_pago,
                "url": reverse("ampliar_oferente"),
            })
    if vendedor:
        for pedido in ventas.filter(estado_comision__in=("pendiente", "reportada", "pagada"))[:40]:
            pagos_hechos.append({
                "cuando": pedido.comision_pagada_en or pedido.creado,
                "que": f"Comisión pedido #{pedido.id}",
                "monto": pedido.comision_cop,
                "estado": pedido.get_estado_comision_display(),
                "url": reverse("liquidar_comision"),
            })
    pagos_hechos.sort(key=lambda f: f["cuando"] or 0, reverse=True)

    cobro_alta = None
    cobro_mes = None
    wompi_alta = None
    wompi_mes = None
    if oferente:
        if not oferente.inscripcion_pagada:
            cobro_alta = abrir_cobro_inscripcion(oferente)
            if cobro_alta and wompi.checkout_listo() and cobro_alta.estado_pago != "aprobado":
                destino = request.build_absolute_uri(reverse("resultado_activacion"))
                wompi_alta = wompi.contexto_widget(cobro_alta, destino)
        cobro_mes = abrir_cobro_mensual(oferente)
        if cobro_mes and wompi.checkout_listo() and cobro_mes.estado_pago != "aprobado":
            destino = request.build_absolute_uri(reverse("resultado_mensualidad"))
            wompi_mes = wompi.contexto_widget(cobro_mes, destino)

    recibido = Decimal("0")
    if vendedor:
        recibido += ventas.filter(giro__estado="pagado").aggregate(s=Sum("neto_vendedor"))["s"] or 0
    if oferente:
        recibido += GiroCita.objects.filter(cita__oferente=oferente, estado="pagado").aggregate(s=Sum("monto_cop"))["s"] or 0

    deudas = []
    por_pagar = Decimal("0")
    if cobro_alta and cobro_alta.estado_pago != "aprobado":
        deudas.append({"que": "Inscripción de oferente (incluye el primer mes)", "monto": cobro_alta.monto_cop, "url": reverse("activar_oferente")})
        por_pagar += cobro_alta.monto_cop or 0
    if cobro_mes and cobro_mes.estado_pago != "aprobado":
        deudas.append({"que": "Mensualidad de oferente", "monto": cobro_mes.monto_cop, "url": reverse("mensualidad_oferente")})
        por_pagar += cobro_mes.monto_cop or 0
    if oferente:
        for extra in oferente.pagos_extra.filter(estado_pago="pendiente")[:8]:
            deudas.append({"que": extra.get_tipo_display(), "monto": extra.monto_cop, "url": reverse("ampliar_oferente")})
            por_pagar += extra.monto_cop or 0
    for pedido in compras:
        if pedido.estado_pago not in ("aprobado",):
            deudas.append({"que": f"Pedido #{pedido.id} por pagar", "monto": pedido.monto_cop, "url": reverse("conversacion_pedido", args=[pedido.id])})
            por_pagar += pedido.monto_cop or 0
    for cita in citas_contratadas:
        if cita.estado_pago != "aprobado":
            deudas.append({"que": f"Cita con {cita.oferente.nombre}", "monto": cita.monto_cop, "url": f"{reverse('resultado_cita', args=[cita.id])}?clave={cita.clave_contacto}"})
            por_pagar += cita.monto_cop or 0
    if vendedor:
        deuda_com = ventas.filter(estado_comision__in=("pendiente", "reportada")).aggregate(s=Sum("comision_cop"))["s"] or 0
        if deuda_com:
            deudas.append({"que": "Comisión de ventas por liquidar", "monto": deuda_com, "url": reverse("liquidar_comision")})
            por_pagar += deuda_com

    staff_giros = []
    staff_oficios = []
    saldo_era = None
    if user.is_staff:
        staff_giros = list(
            Giro.objects.exclude(estado="pagado")
            .select_related("pedido", "pedido__vendedor")
            .order_by("-creado")[:80]
        )
        staff_oficios = list(
            GiroCita.objects.exclude(estado="pagado")
            .select_related("cita", "cita__oferente", "cita__comentario")
            .order_by("-creado")[:80]
        )
        from pedidos.services.giros import saldo_era_en_wompi
        saldo_era = saldo_era_en_wompi()

    return render(request, "cuentas/tablero.html", {
        "vendedor": vendedor,
        "comprador": comprador,
        "cliente": cliente,
        "oferente": oferente,
        "ventas": ventas[:80] if vendedor else ventas,
        "compras": compras,
        "citas_contratadas": citas_contratadas,
        "citas_recibidas": citas_recibidas[:80] if oferente else citas_recibidas,
        "consultas_hechas": consultas_hechas,
        "consultas_recibidas": consultas_recibidas,
        "giros_venta": giros_venta,
        "giros_oficio": giros_oficio,
        "despachos": despachos,
        "pagos_hechos": pagos_hechos[:60],
        "recibido": recibido,
        "cobro_alta": cobro_alta,
        "cobro_mes": cobro_mes,
        "wompi_alta": wompi_alta,
        "wompi_mes": wompi_mes,
        "tarjeta_lista": wompi.checkout_listo(),
        "cuota": cuota_activacion(),
        "mensualidad": cuota_mensualidad(),
        "primera": cuota_primera(),
        "deudas": deudas[:40],
        "por_pagar": por_pagar,
        "es_staff": user.is_staff,
        "staff_giros": staff_giros,
        "staff_oficios": staff_oficios,
        "saldo_era": saldo_era,
    })
