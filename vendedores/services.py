from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, F, Max, Min
from django.utils import timezone

from pedidos.models import Pedido
from productos.models import Producto

from .opciones import banda_precio


def peso(valor):
    return Decimal(str(valor or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def porcentajes_comision():
    """Los porcentajes vivos los define el dueño. Cada pedido guarda el que usó."""
    from pedidos.models import CuentaPlataforma

    cuenta = CuentaPlataforma.objects.filter(pk=1).first()
    detalle = Decimal(str(getattr(settings, "COMISION_PCT", 10)))
    mayor = Decimal(str(getattr(settings, "COMISION_MAYOR_PCT", 5)))
    if cuenta is not None:
        detalle = Decimal(str(cuenta.comision_detalle_pct))
        mayor = Decimal(str(cuenta.comision_mayor_pct))
    return detalle, mayor


def tarifa_wompi(monto):
    """2,65% + $700, y el IVA del 19% solo sobre esa tarifa. Wompi no permite quitarlo."""
    monto = Decimal(str(monto or 0))
    pct = Decimal(str(getattr(settings, "WOMPI_PCT", "2.65")))
    fijo = Decimal(str(getattr(settings, "WOMPI_FIJO_COP", 700)))
    iva = Decimal(str(getattr(settings, "WOMPI_IVA_PCT", 19)))
    base = monto * pct / Decimal("100") + fijo
    return peso(base * (Decimal("1") + iva / Decimal("100")))


def iva_mercancia(base, con_iva):
    if not con_iva:
        return Decimal("0"), Decimal("0")
    pct = (Decimal(str(getattr(settings, "IVA_COLOMBIA", "0.19"))) * Decimal("100")).quantize(Decimal("0.01"))
    return pct, peso(Decimal(str(base or 0)) * pct / Decimal("100"))


def total_con_cargos(base, pct):
    """Suma el porcentaje de ERA shop y la tarifa de Wompi al valor del pedido.

    El proveedor recibe la base. El cliente paga la base más esos dos cargos.
    La tarifa se calcula sobre el total que entra a Wompi.
    """
    base = peso(base)
    porcentaje = Decimal(str(pct or 0)) / Decimal("100")
    comision = peso(base * porcentaje)
    variable = Decimal(str(getattr(settings, "WOMPI_PCT", "2.65"))) / Decimal("100")
    fijo = Decimal(str(getattr(settings, "WOMPI_FIJO_COP", 700)))
    factor = Decimal("1") + Decimal(str(getattr(settings, "WOMPI_IVA_PCT", 19))) / Decimal("100")
    denominador = Decimal("1") - variable * factor
    total = peso((base * (Decimal("1") + porcentaje) + fijo * factor) / denominador)
    tarifa = tarifa_wompi(total)
    for _ in range(4):
        ajustado = peso(base + comision + tarifa)
        if ajustado == total:
            break
        total = ajustado
        tarifa = tarifa_wompi(total)
    tarifa = peso(total - base - comision)
    return {
        "base": base,
        "total": total,
        "comision": comision,
        "tarifa": tarifa,
        "neto": base,
    }


def aplicar_comision(pedido):
    """En mostrador el vendedor asume los cargos. Al por mayor se le suman al cliente."""
    if not pedido.vendedor_id:
        pedido.comision_pct = 0
        pedido.comision_cop = 0
        pedido.tarifa_pasarela_cop = 0
        pedido.neto_vendedor = pedido.monto_cop or 0
        pedido.estado_comision = "exenta"
        return
    detalle, mayor = porcentajes_comision()
    if pedido.es_mayor:
        pct = mayor
        base = peso(Decimal(str(pedido.subtotal_cop or 0)) + Decimal(str(pedido.iva_cop or 0)))
        cargos = total_con_cargos(base, pct)
        pedido.comision_pct = pct
        pedido.comision_cop = cargos["comision"]
        pedido.tarifa_pasarela_cop = cargos["tarifa"]
        pedido.neto_vendedor = cargos["neto"]
        pedido.monto_cop = cargos["total"]
    else:
        pct = detalle
        monto = Decimal(str(pedido.monto_cop or 0))
        comision = peso(monto * pct / Decimal("100"))
        tarifa = tarifa_wompi(monto)
        pedido.comision_pct = pct
        pedido.comision_cop = comision
        pedido.tarifa_pasarela_cop = tarifa
        neto = monto - comision - tarifa
        pedido.neto_vendedor = neto if neto > 0 else 0
    if pedido.estado_comision in ("", "exenta"):
        pedido.estado_comision = "por_confirmar"


def activar_cobro_comision(pedido):
    """La liquidación corre cuando el cliente ya pagó."""
    if not pedido.vendedor_id or pedido.estado_comision != "por_confirmar":
        return
    dias = int(getattr(settings, "DIAS_LIQUIDACION", 5))
    pedido.estado_comision = "pendiente"
    pedido.fecha_limite_comision = timezone.now() + timedelta(days=dias)
    pedido.save(update_fields=["estado_comision", "fecha_limite_comision"])


def reclasificar_vendedor(vendedor):
    stats = Producto.objects.filter(vendedor=vendedor, activo=True).aggregate(
        mn=Min("precio_final_cop"),
        mx=Max("precio_final_cop"),
        prom=Avg("precio_final_cop"),
    )
    if stats["prom"] is None:
        return
    vendedor.precio_desde = stats["mn"]
    vendedor.precio_hasta = stats["mx"]
    vendedor.rango_precio = banda_precio(stats["prom"])
    vendedor.save(update_fields=["precio_desde", "precio_hasta", "rango_precio"])


@transaction.atomic
def expulsar_vendedor(vendedor, motivo):
    from .models import Vendedor

    vendedor = Vendedor.objects.select_for_update().get(pk=vendedor.pk)
    if vendedor.estado != "expulsado":
        vendedor.estado = "expulsado"
        vendedor.motivo_sancion = motivo
        vendedor.fecha_sancion = timezone.now()
        vendedor.save(update_fields=["estado", "motivo_sancion", "fecha_sancion"])
    Producto.objects.filter(vendedor=vendedor, activo=True).update(activo=False)
    return vendedor


def aplicar_sanciones():
    """Quien no liquida el 10% a tiempo sale del catálogo."""
    ahora = timezone.now()
    vencidos = (
        Pedido.objects.filter(
            estado_comision="pendiente",
            fecha_limite_comision__lt=ahora,
            vendedor__isnull=False,
        )
        .select_related("vendedor")
        .order_by("fecha_limite_comision")
    )
    retirados = 0
    ya = set()
    for pedido in vencidos:
        pedido.estado_comision = "vencida"
        pedido.save(update_fields=["estado_comision"])
        if pedido.vendedor_id in ya or pedido.vendedor.estado == "expulsado":
            ya.add(pedido.vendedor_id)
            continue
        pct = pedido.comision_pct or getattr(settings, "COMISION_PCT", 10)
        expulsar_vendedor(
            pedido.vendedor,
            f"No liquidó la comisión del {pct}% del pedido #{pedido.id}. "
            "La tienda fue retirada de la página.",
        )
        ya.add(pedido.vendedor_id)
        retirados += 1
    return retirados


def devolver_stock(pedido):
    lineas = list(pedido.lineas.all()) if pedido.pk else []
    if lineas:
        for linea in lineas:
            if linea.producto_id and linea.cantidad:
                Producto.objects.filter(pk=linea.producto_id, controla_stock=True).update(
                    stock=F("stock") + linea.cantidad
                )
        return
    if not pedido.producto_id or not pedido.cantidad:
        return
    Producto.objects.filter(pk=pedido.producto_id, controla_stock=True).update(
        stock=F("stock") + pedido.cantidad
    )


@transaction.atomic
def cancelar_pedido_vendedor(pedido, vendedor, acepta_sancion):
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if pedido.estado in ("fallido", "entregado"):
        return "cerrado"
    if pedido.estado_comision == "pagada":
        return "ya_liquidada"
    if pedido.estado_comision == "retenida":
        from pedidos.models import Giro

        giro = Giro.objects.filter(pedido=pedido).first()
        if giro and giro.estado in ("enviado", "pagado"):
            return "giro_en_curso"
        if giro:
            giro.estado = "rechazado"
            giro.detalle = "El pedido se anuló antes de consignar el restante."
            giro.save()
        pedido.estado = "fallido"
        pedido.estado_comision = "anulada"
        nota = "Pedido anulado. El restante del vendedor todavía no había salido."
        pedido.notas = f"{pedido.notas}\n{nota}".strip() if pedido.notas else nota
        pedido.save()
        devolver_stock(pedido)
        return "giro_cancelado"
    if pedido.estado_comision in ("pendiente", "reportada"):
        if not acepta_sancion:
            return "falta_aceptar"
        pedido.estado = "fallido"
        pedido.estado_comision = "vencida"
        nota = "El vendedor canceló la venta con la comisión ya generada."
        pedido.notas = f"{pedido.notas}\n{nota}".strip() if pedido.notas else nota
        pedido.save()
        devolver_stock(pedido)
        pct = pedido.comision_pct or getattr(settings, "COMISION_PCT", 10)
        expulsar_vendedor(
            vendedor,
            f"Canceló el pedido #{pedido.id} con la comisión del {pct}% pendiente. "
            "La tienda fue retirada de la página.",
        )
        return "expulsado"
    pedido.estado = "fallido"
    pedido.estado_comision = "anulada"
    nota = "Pedido anulado antes del pago del cliente. No hubo comisión."
    pedido.notas = f"{pedido.notas}\n{nota}".strip() if pedido.notas else nota
    pedido.save()
    devolver_stock(pedido)
    return "anulado"
