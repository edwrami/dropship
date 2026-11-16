import re
import time
from decimal import Decimal

import requests
from django.conf import settings
from pedidos.services import giros as giros_base
from pedidos.services import wompi
from vendedores.services import porcentajes_comision, peso, tarifa_wompi

from .models import Cita, Cobertura, Especialidad, GiroCita, PagoActivacion, PagoCita, PagoExtra


def cuota_activacion():
    return Decimal(str(getattr(settings, "CUOTA_SERVICIO_COP", 100000)))


def nueva_referencia(prefijo, pk):
    return f"{prefijo}-{pk}-{int(time.time())}"


def aplicar_comision_cita(cita):
    detalle, _mayor = porcentajes_comision()
    monto = Decimal(str(cita.monto_cop or 0))
    comision = peso(monto * detalle / Decimal("100"))
    tarifa = tarifa_wompi(monto)
    cita.comision_pct = detalle
    cita.comision_cop = comision
    cita.tarifa_pasarela_cop = tarifa
    neto = monto - comision - tarifa
    cita.neto_vendedor = neto if neto > 0 else 0
    if cita.estado_comision in ("", "exenta"):
        cita.estado_comision = "por_confirmar"


def contexto_cobro(cobro, redirect_url):
    return wompi.contexto_widget(cobro, redirect_url)


def aplicar_transaccion(tx):
    ref = (tx.get("reference") or "").strip()
    if not ref:
        return False
    activacion = PagoActivacion.objects.filter(referencia_pago=ref).select_related("oferente").first()
    if activacion:
        _activar(activacion, tx)
        return True
    extra = PagoExtra.objects.filter(referencia_pago=ref).select_related(
        "oferente", "cobertura", "especialidad",
    ).first()
    if extra:
        _activar_extra(extra, tx)
        return True
    cita = Cita.objects.filter(referencia_pago=ref).select_related("oferente").first()
    if cita:
        _cobrar_cita(cita, tx)
        return True
    return False


def _estado_wompi(tx):
    return (tx.get("status") or "").upper()


def _activar(cobro, tx):
    status = _estado_wompi(tx)
    cobro.wompi_id = tx.get("id") or cobro.wompi_id
    cobro.metodo_pago = tx.get("payment_method_type") or cobro.metodo_pago
    if status == "APPROVED":
        cobro.estado_pago = "aprobado"
        cobro.save()
        oferente = cobro.oferente
        if oferente.estado == "pendiente_pago":
            oferente.estado = "activo"
            oferente.save(update_fields=["estado"])
        _sembrar_incluido(oferente)
    elif status in ("DECLINED", "VOIDED"):
        cobro.estado_pago = "declinado"
        cobro.save()
    elif status == "ERROR":
        cobro.estado_pago = "error"
        cobro.save()
    elif cobro.estado_pago != "aprobado":
        cobro.estado_pago = "reportado"
        cobro.save()


def _cobrar_cita(cita, tx):
    status = _estado_wompi(tx)
    cita.wompi_id = tx.get("id") or cita.wompi_id
    cita.metodo_pago = tx.get("payment_method_type") or cita.metodo_pago
    if status == "APPROVED":
        cita.estado_pago = "aprobado"
        if cita.estado == "pendiente":
            cita.estado = "pagado"
        cita.estado_comision = "por_confirmar"
        cita.save()
        _registrar_pago(cita, "aprobado")
    elif status in ("DECLINED", "VOIDED"):
        cita.estado_pago = "declinado"
        cita.estado = "liberado"
        cita.save()
        _registrar_pago(cita, "declinado")
    elif status == "ERROR":
        cita.estado_pago = "error"
        cita.save()
        _registrar_pago(cita, "error")
    elif cita.estado_pago != "aprobado":
        cita.estado_pago = "reportado"
        cita.save()
        _registrar_pago(cita, "reportado")


def _activar_extra(cobro, tx):
    status = _estado_wompi(tx)
    cobro.wompi_id = tx.get("id") or cobro.wompi_id
    cobro.metodo_pago = tx.get("payment_method_type") or cobro.metodo_pago
    if status == "APPROVED":
        cobro.estado_pago = "aprobado"
        cobro.save()
        if cobro.cobertura_id:
            cobro.cobertura.activa = True
            cobro.cobertura.save(update_fields=["activa"])
        if cobro.especialidad_id:
            cobro.especialidad.activa = True
            cobro.especialidad.save(update_fields=["activa"])
    elif status in ("DECLINED", "VOIDED"):
        cobro.estado_pago = "declinado"
        cobro.save()
    elif status == "ERROR":
        cobro.estado_pago = "error"
        cobro.save()
    elif cobro.estado_pago != "aprobado":
        cobro.estado_pago = "reportado"
        cobro.save()


def _sembrar_incluido(oferente):
    cob, _c = Cobertura.objects.get_or_create(
        oferente=oferente,
        departamento=oferente.departamento,
        municipio=oferente.ciudad,
        defaults={"incluida": True, "activa": True},
    )
    if not cob.activa:
        cob.incluida = True
        cob.activa = True
        cob.save(update_fields=["incluida", "activa"])
    esp, _e = Especialidad.objects.get_or_create(
        oferente=oferente,
        rubro=oferente.rubro,
        oficio=oferente.oficio,
        defaults={
            "precio_cop": oferente.precio_cop,
            "unidad": oferente.unidad,
            "modo_tiempo": "cita" if oferente.unidad not in ("dia", "semana") else oferente.unidad,
            "duracion_minutos": oferente.duracion_minutos,
            "incluida": True,
            "activa": True,
        },
    )
    if not esp.activa:
        esp.incluida = True
        esp.activa = True
        esp.save(update_fields=["incluida", "activa"])


def liberar_giro_si_realizado(cita):
    if cita.estado_pago != "aprobado" or not cita.trabajo_realizado:
        return None
    cita.estado = "realizado"
    cita.estado_comision = "retenida"
    cita.save(update_fields=["estado", "estado_comision"])
    return repartir_cita(cita)


def _registrar_pago(cita, estado):
    pago, _creado = PagoCita.objects.get_or_create(
        cita=cita,
        defaults={
            "monto_cop": cita.monto_cop,
            "metodo": cita.metodo_pago or "pagina",
            "estado": estado,
            "referencia": cita.referencia_pago or "",
            "wompi_id": cita.wompi_id,
            "origen": "wompi",
        },
    )
    pago.monto_cop = cita.monto_cop
    pago.metodo = cita.metodo_pago or pago.metodo
    pago.estado = estado
    pago.referencia = cita.referencia_pago or pago.referencia
    pago.wompi_id = cita.wompi_id
    pago.origen = "wompi"
    pago.save()


def repartir_cita(cita):
    giro, _creado = GiroCita.objects.get_or_create(
        cita=cita,
        defaults={
            "monto_cop": cita.neto_vendedor or 0,
            "comision_cop": cita.comision_cop or 0,
            "destino_nequi": (cita.oferente.nequi or "")[:20],
        },
    )
    if giro.estado == "pagado":
        return giro
    giro.monto_cop = cita.neto_vendedor or 0
    giro.comision_cop = cita.comision_cop or 0
    giro.destino_nequi = (cita.oferente.nequi or "")[:20]
    oferente = cita.oferente
    if giro.payout_id:
        giro.estado = "enviado"
        giro.save()
        return giro
    nequi = re.sub(r"\D", "", giro.destino_nequi or "")
    documento = re.sub(r"\D", "", oferente.documento or "")
    email = ""
    if oferente.user_id:
        email = (oferente.user.email or "").strip()
    email = email or (oferente.email or "").strip()
    if len(nequi) != 10 or not documento or not email or not (oferente.responsable or "").strip():
        giro.estado = "sin_datos"
        giro.detalle = "El oferente debe tener Nequi, cédula, nombre y correo."
        giro.save()
        return giro
    if int(giro.monto_cop or 0) <= 0:
        giro.estado = "rechazado"
        giro.detalle = "El valor para el oferente es cero."
        giro.save()
        return giro
    cuenta = giros_base._cuenta()
    if not giros_base._llaves(cuenta):
        giro.estado = "pendiente"
        giro.detalle = "El restante queda anotado. ERA shop lo consigna a mano al Nequi del oferente."
        giro.save()
        return giro
    banco = giros_base._banco_nequi(cuenta)
    origen = cuenta.payouts_account_id or giros_base._cuenta_origen(cuenta)
    if not banco or not origen:
        giro.estado = "pendiente"
        giro.detalle = "Wompi aún no muestra la cuenta de origen o el banco Nequi."
        giro.save()
        return giro
    cuerpo = {
        "reference": f"giro-srv-{cita.id}",
        "accountId": origen,
        "paymentType": "OTHER",
        "transactions": [{
            "legalIdType": "NIT" if len(documento) > 10 else "CC",
            "legalId": documento[:20],
            "bankId": banco,
            "accountType": "AHORROS",
            "accountNumber": nequi,
            "name": oferente.responsable[:80],
            "email": email[:120],
            "amount": int(giro.monto_cop) * 100,
            "reference": f"giro-srv-{cita.id}",
        }],
    }
    try:
        respuesta = requests.post(
            f"{giros_base.BASE}/payouts",
            headers=giros_base._headers(cuenta, f"giro-srv-{cita.id}"),
            json=cuerpo,
            timeout=20,
        )
    except requests.RequestException:
        giro.estado = "pendiente"
        giro.detalle = "No se pudo ordenar el giro. Quedó pendiente."
        giro.save()
        return giro
    if respuesta.status_code >= 400:
        giro.estado = "pendiente"
        giro.detalle = giros_base._mensaje_error(respuesta)[:300]
        giro.save()
        return giro
    data = respuesta.json() if respuesta.content else {}
    giro.payout_id = str(giros_base._buscar(data, "payoutId") or giros_base._buscar(data, "id") or "")[:80]
    giro.estado = "enviado"
    giro.detalle = "Wompi está procesando el giro al Nequi del oferente."
    giro.save()
    return giro
