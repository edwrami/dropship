import re
from decimal import Decimal
from types import SimpleNamespace

import requests
from django.db.models import Sum
from django.utils import timezone

from pedidos.models import CuentaPlataforma, Giro, MensajePedido, Pedido, RetiroPlataforma

BASE = "https://api.payouts.wompi.co/v1"


def repartir(pedido):
    """Anota el restante del vendedor. El dinero se queda en Wompi hasta que ERA shop autorice el giro."""
    if not pedido.vendedor_id:
        return None
    if pedido.estado_comision not in ("anulada", "vencida", "retenida", "pagada"):
        pedido.estado_comision = "retenida"
        pedido.comision_pagada_en = timezone.now()
        pedido.fecha_limite_comision = None
        pedido.save(update_fields=["estado_comision", "comision_pagada_en", "fecha_limite_comision"])
    vendedor = pedido.vendedor
    giro, creado = Giro.objects.get_or_create(
        pedido=pedido,
        defaults={
            "monto_cop": pedido.neto_vendedor or 0,
            "comision_cop": pedido.comision_cop or 0,
            "destino_nequi": (vendedor.nequi or "")[:20],
        },
    )
    if giro.estado in ("pagado", "enviado"):
        return giro
    giro.monto_cop = pedido.neto_vendedor or 0
    giro.comision_cop = pedido.comision_cop or 0
    giro.destino_nequi = (vendedor.nequi or giro.destino_nequi or "")[:20]
    if not giro.payout_id:
        giro.estado = "pendiente"
        giro.detalle = "El dinero sigue en Wompi. ERA shop autoriza el giro al Nequi."
        giro.save()
    if creado:
        _anotar(pedido, giro)
    return giro


def autorizar_giro_venta(giro):
    """Saca de Wompi el restante y lo manda al Nequi del vendedor. Solo con autorización."""
    if giro is None or giro.estado in ("pagado", "enviado"):
        return giro
    pedido = giro.pedido
    if pedido.estado_pago != "aprobado" or not pedido.vendedor_id:
        return giro
    giro.monto_cop = pedido.neto_vendedor or giro.monto_cop
    giro.destino_nequi = (pedido.vendedor.nequi or giro.destino_nequi or "")[:20]
    _enviar(giro, pedido.vendedor, f"giro-{pedido.id}")
    _anotar(pedido, giro)
    return giro


def actualizar(giro):
    if not giro or giro.estado != "enviado" or not giro.payout_id:
        return giro
    cuenta = _cuenta()
    if not _llaves(cuenta):
        return giro
    try:
        respuesta = requests.get(
            f"{BASE}/payouts/{giro.payout_id}",
            headers=_headers(cuenta),
            timeout=15,
        )
    except requests.RequestException:
        return giro
    if respuesta.status_code != 200:
        return giro
    antes = giro.estado
    _aplicar_estado(giro, respuesta.json())
    giro.save()
    if giro.estado != antes:
        _anotar(giro.pedido, giro)
    return giro


def marcar_pago_manual(pedido, comprobante=""):
    """El dueño ya consignó el 90% al Nequi del vendedor."""
    if not pedido.vendedor_id or pedido.estado_pago != "aprobado":
        return None
    if pedido.estado_comision not in ("anulada", "vencida", "retenida", "pagada"):
        pedido.estado_comision = "retenida"
        pedido.comision_pagada_en = timezone.now()
        pedido.fecha_limite_comision = None
        pedido.save(update_fields=["estado_comision", "comision_pagada_en", "fecha_limite_comision"])
    vendedor = pedido.vendedor
    giro, _creado = Giro.objects.get_or_create(
        pedido=pedido,
        defaults={
            "monto_cop": pedido.neto_vendedor or 0,
            "comision_cop": pedido.comision_cop or 0,
            "destino_nequi": (vendedor.nequi or "")[:20],
        },
    )
    if giro.estado in ("pagado", "enviado"):
        return giro
    giro.monto_cop = pedido.neto_vendedor or 0
    giro.comision_cop = pedido.comision_cop or 0
    giro.destino_nequi = (vendedor.nequi or "")[:20]
    giro.estado = "pagado"
    recibo = f" Comprobante {comprobante}." if comprobante else ""
    giro.detalle = f"ERA shop consignó este restante a mano, al Nequi {giro.destino_nequi}.{recibo}"[:300]
    giro.save()
    _anotar(pedido, giro)
    return giro


def reintentar_pendientes(vendedor=None):
    """No gira solo. Solo actualiza giros que ya autorizaste y Wompi está procesando."""
    qs = Giro.objects.filter(estado="enviado").exclude(payout_id="").select_related("pedido")
    if vendedor is not None:
        qs = qs.filter(pedido__vendedor=vendedor)
    for giro in qs[:40]:
        actualizar(giro)


def _enviar(giro, vendedor, referencia=None):
    if giro.payout_id:
        giro.estado = "enviado"
        giro.save()
        return
    referencia = referencia or f"giro-{getattr(giro, 'pedido_id', giro.pk)}"
    nequi = re.sub(r"\D", "", giro.destino_nequi or "")
    documento = re.sub(r"\D", "", getattr(vendedor, "documento", "") or "")
    email = ""
    if getattr(vendedor, "user_id", None):
        email = (vendedor.user.email or "").strip()
    email = email or (getattr(vendedor, "email", "") or "").strip()
    nombre = (getattr(vendedor, "responsable", "") or getattr(vendedor, "titular", "") or "").strip()
    if len(nequi) != 10 or not documento or not email or not nombre:
        giro.estado = "sin_datos"
        giro.detalle = "Faltan Nequi de 10 dígitos, cédula, nombre y correo para el giro."
        giro.save()
        return
    if int(giro.monto_cop or 0) <= 0:
        giro.estado = "rechazado"
        giro.detalle = "El valor a girar es cero."
        giro.save()
        return
    cuenta = _cuenta()
    if not _llaves(cuenta):
        giro.estado = "pendiente"
        giro.detalle = "Faltan las llaves de Pagos a terceros. El dinero sigue en Wompi hasta que las conectes y autorices."
        giro.save()
        return
    banco = _banco_nequi(cuenta)
    origen = cuenta.payouts_account_id or _cuenta_origen(cuenta)
    if not banco or not origen:
        giro.estado = "pendiente"
        giro.detalle = "Wompi aún no muestra la cuenta de origen o el banco Nequi."
        giro.save()
        return
    if not cuenta.payouts_account_id:
        cuenta.payouts_account_id = origen[:80]
        cuenta.save(update_fields=["payouts_account_id"])
    cuerpo = {
        "reference": referencia[:80],
        "accountId": origen,
        "paymentType": "OTHER",
        "transactions": [{
            "legalIdType": "NIT" if len(documento) > 10 else "CC",
            "legalId": documento[:20],
            "bankId": banco,
            "accountType": "AHORROS",
            "accountNumber": nequi,
            "name": nombre[:80],
            "email": email[:120],
            "amount": int(giro.monto_cop) * 100,
            "reference": referencia[:80],
        }],
    }
    respuesta = requests.post(
        f"{BASE}/payouts",
        headers=_headers(cuenta, referencia[:64]),
        json=cuerpo,
        timeout=20,
    )
    if respuesta.status_code >= 400:
        texto = _mensaje_error(respuesta)
        if "fondo" in texto.lower() or "insufficient" in texto.lower() or "D19" in texto:
            giro.estado = "pendiente"
            giro.detalle = "Wompi todavía no tiene saldo disponible para este giro."
        else:
            giro.estado = "rechazado"
            giro.detalle = texto[:300]
        giro.save()
        return
    data = respuesta.json() if respuesta.content else {}
    giro.payout_id = str(_buscar(data, "payoutId") or _buscar(data, "id") or "")[:80]
    _aplicar_estado(giro, data)
    if giro.estado == "pendiente":
        giro.estado = "enviado"
    giro.save()


def _aplicar_estado(giro, data):
    estado = str(_buscar(data, "status") or "").upper()
    if estado in ("TOTAL_PAYMENT", "APPROVED"):
        giro.estado = "pagado"
        giro.detalle = "Wompi confirmó el abono al Nequi del vendedor."
    elif estado in ("REJECTED", "NOT_APPROVED", "FAILED", "CANCELLED"):
        giro.estado = "rechazado"
        giro.detalle = "Wompi rechazó el giro."
    elif estado == "PENDING_APPROVAL":
        giro.estado = "enviado"
        giro.detalle = "Wompi lo dejó pendiente de aprobación en el panel del comercio."
    elif estado:
        giro.estado = "enviado"
        giro.detalle = "Wompi está procesando el giro al Nequi del vendedor."


def _cuenta():
    return CuentaPlataforma.objects.order_by("id").first()


def _llaves(cuenta):
    return bool(cuenta and cuenta.payouts_api_key and cuenta.payouts_user_id)


def _headers(cuenta, idempotencia=None):
    headers = {
        "x-api-key": cuenta.payouts_api_key,
        "user-principal-id": cuenta.payouts_user_id,
        "Content-Type": "application/json",
    }
    if idempotencia:
        headers["idempotency-key"] = idempotencia[:64]
    return headers


def _banco_nequi(cuenta):
    respuesta = requests.get(f"{BASE}/banks", headers=_headers(cuenta), timeout=15)
    if respuesta.status_code != 200:
        return ""
    for banco in _listas(respuesta.json()):
        nombre = str(banco.get("name") or banco.get("bankName") or "").upper()
        if "NEQUI" in nombre:
            return str(banco.get("id") or banco.get("bankId") or "")
    return ""


def _cuenta_origen(cuenta):
    respuesta = requests.get(f"{BASE}/accounts", headers=_headers(cuenta), timeout=15)
    if respuesta.status_code != 200:
        return ""
    for item in _listas(respuesta.json()):
        identificador = item.get("id") or item.get("accountId")
        if identificador:
            return str(identificador)
    return ""


def _listas(data):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for valor in data.values():
            hallados = _listas(valor)
            if hallados:
                return hallados
    return []


def _buscar(data, clave):
    if isinstance(data, dict):
        if data.get(clave):
            return data[clave]
        for valor in data.values():
            hallado = _buscar(valor, clave)
            if hallado:
                return hallado
    elif isinstance(data, list):
        for item in data:
            hallado = _buscar(item, clave)
            if hallado:
                return hallado
    return ""


def _mensaje_error(respuesta):
    try:
        data = respuesta.json()
    except ValueError:
        return "Wompi rechazó el giro."
    texto = _buscar(data, "message") or _buscar(data, "error") or ""
    return str(texto or "Wompi rechazó el giro.")[:300]


def _anotar(pedido, giro):
    MensajePedido.objects.create(
        pedido=pedido,
        autor="plataforma",
        nombre="ERA shop",
        texto=(
            f"De esta venta, ${giro.comision_cop} queda para ERA shop, "
            f"${pedido.tarifa_pasarela_cop} es la tarifa de Wompi y "
            f"${giro.monto_cop} es para la tienda"
            f"{f', Nequi {giro.destino_nequi}' if giro.destino_nequi else ''}. "
            f"{giro.get_estado_display()}. {giro.detalle}"
        ).strip(),
    )


def saldo_era_en_wompi():
    """Lo de ERA shop que sigue en Wompi: cuotas e inscripciones + comisiones, menos retiros ya enviados."""
    from servicios.models import Cita, PagoActivacion, PagoExtra, PagoMensualidad

    total = Decimal("0")
    total += PagoActivacion.objects.filter(estado_pago="aprobado").aggregate(s=Sum("monto_cop"))["s"] or 0
    total += PagoMensualidad.objects.filter(estado_pago="aprobado").aggregate(s=Sum("monto_cop"))["s"] or 0
    total += PagoExtra.objects.filter(estado_pago="aprobado").aggregate(s=Sum("monto_cop"))["s"] or 0
    total += Pedido.objects.filter(estado_pago="aprobado").aggregate(s=Sum("comision_cop"))["s"] or 0
    total += Cita.objects.filter(estado_pago="aprobado").aggregate(s=Sum("comision_cop"))["s"] or 0
    salido = RetiroPlataforma.objects.filter(estado__in=("enviado", "pagado")).aggregate(s=Sum("monto_cop"))["s"] or 0
    queda = total - salido
    return queda if queda > 0 else Decimal("0")


def retirar_a_mi_nequi(monto):
    """Autoriza sacar de Wompi la comisión/cuotas de ERA shop hacia el Nequi de la cuenta."""
    cuenta = _cuenta()
    if cuenta is None:
        return None, "Guarda primero tu Nequi, cédula y correo en Ventas."
    try:
        monto = Decimal(str(monto or 0))
    except Exception:
        return None, "Escribe un monto válido."
    monto = monto.quantize(Decimal("1"))
    if monto <= 0:
        return None, "El monto debe ser mayor a cero."
    disponible = saldo_era_en_wompi()
    if monto > disponible:
        return None, f"En Wompi de ERA shop hay ${disponible}. No puedes retirar más."
    retiro = RetiroPlataforma.objects.create(
        monto_cop=monto,
        destino_nequi=(cuenta.nequi or "")[:20],
        estado="pendiente",
        detalle="Autorizado. Saliendo de Wompi a tu Nequi.",
    )
    persona = SimpleNamespace(
        documento=cuenta.documento or "",
        responsable=cuenta.titular or "ERA shop",
        email=cuenta.email or "",
        user_id=None,
        user=None,
        titular=cuenta.titular or "ERA shop",
    )
    retiro.destino_nequi = (cuenta.nequi or "")[:20]
    _enviar(retiro, persona, f"era-{retiro.id}")
    return retiro, None
