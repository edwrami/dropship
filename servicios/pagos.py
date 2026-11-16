import time
from decimal import Decimal

from django.conf import settings
from pedidos.services import giros as giros_base
from pedidos.services import wompi
from vendedores.services import porcentajes_comision, peso, tarifa_wompi

from datetime import timedelta

from django.utils import timezone

from django.core.exceptions import ObjectDoesNotExist

from .models import (
    Cita, Cobertura, Comentario, Especialidad, GiroCita,
    PagoActivacion, PagoCita, PagoExtra, PagoMensualidad,
)


def cuota_activacion():
    return Decimal(str(getattr(settings, "CUOTA_SERVICIO_COP", 100000)))


def cuota_mensualidad():
    return Decimal(str(getattr(settings, "MENSUALIDAD_SERVICIO_COP", 50000)))


def cuota_primera():
    """Inscripción de $100.000: incluye el primer mes de visibilidad."""
    return cuota_activacion()


def abrir_cobro_inscripcion(oferente):
    """Un solo Wompi de $100.000: inscripción + primer mes. Los meses siguientes salen a $50.000."""
    if oferente is None:
        return None
    cobro, _creado = PagoActivacion.objects.get_or_create(
        oferente=oferente,
        defaults={
            "monto_cop": cuota_primera(),
            "referencia_pago": nueva_referencia("ACT", oferente.id),
        },
    )
    if cobro.estado_pago != "aprobado" and cobro.monto_cop != cuota_primera():
        cobro.monto_cop = cuota_primera()
        cobro.referencia_pago = nueva_referencia("ACT", oferente.id)
        cobro.estado_pago = "pendiente"
        cobro.save(update_fields=["monto_cop", "referencia_pago", "estado_pago"])
    return cobro


def abrir_cobro_mensual(oferente):
    """Crea solo el cobro del mes cuando toca. El oferente paga en Wompi; si no paga, deja de aparecer."""
    if oferente is None:
        return None
    act = getattr(oferente, "activacion", None)
    inscrito = act is not None and act.estado_pago == "aprobado"
    if not inscrito and oferente.estado not in ("activo", "pendiente_mensualidad"):
        return None
    ahora = timezone.now()
    if inscrito and not oferente.mensualidad_al_dia and oferente.estado == "activo":
        oferente.estado = "pendiente_mensualidad"
        oferente.save(update_fields=["estado"])
    limite = ahora + timedelta(days=5)
    if oferente.mensualidad_hasta and oferente.mensualidad_hasta > limite:
        return None
    cobro = (
        PagoMensualidad.objects.filter(oferente=oferente, estado_pago="pendiente")
        .order_by("-id")
        .first()
    )
    if cobro:
        return cobro
    cobro = PagoMensualidad.objects.create(
        oferente=oferente,
        monto_cop=cuota_mensualidad(),
        referencia_pago=nueva_referencia("MEN", oferente.id),
    )
    if oferente.user_id:
        from pedidos.avisos import dejar_aviso

        dejar_aviso(
            [oferente.user],
            "Mensualidad de oferente",
            "ERA shop te abrió el cobro de $50.000 para seguir apareciendo este mes.",
            "/servicios/mensualidad/",
        )
    return cobro


def extender_mensualidad(oferente):
    ahora = timezone.now()
    base = oferente.mensualidad_hasta if oferente.mensualidad_hasta and oferente.mensualidad_hasta > ahora else ahora
    oferente.mensualidad_hasta = base + timedelta(days=30)
    act = getattr(oferente, "activacion", None)
    inscrito = act is not None and act.estado_pago == "aprobado"
    if inscrito or oferente.estado in ("activo", "pendiente_mensualidad"):
        oferente.estado = "activo"
    oferente.save(update_fields=["mensualidad_hasta", "estado"])
    return oferente.mensualidad_hasta


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
    mensual = PagoMensualidad.objects.filter(referencia_pago=ref).select_related("oferente").first()
    if mensual:
        _cobrar_mensualidad(mensual, tx)
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
        ya = cobro.estado_pago == "aprobado"
        cobro.estado_pago = "aprobado"
        cobro.save()
        if ya:
            return
        oferente = cobro.oferente
        extender_mensualidad(oferente)
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


def _cobrar_mensualidad(cobro, tx):
    status = _estado_wompi(tx)
    cobro.wompi_id = tx.get("id") or cobro.wompi_id
    cobro.metodo_pago = tx.get("payment_method_type") or cobro.metodo_pago
    if status == "APPROVED":
        if cobro.estado_pago == "aprobado":
            cobro.save()
            return
        cobro.estado_pago = "aprobado"
        hasta = extender_mensualidad(cobro.oferente)
        cobro.cubre_hasta = hasta
        cobro.save()
    elif status in ("DECLINED", "VOIDED"):
        cobro.estado_pago = "declinado"
        cobro.save()
    elif status == "ERROR":
        cobro.estado_pago = "error"
        cobro.save()
    elif cobro.estado_pago != "aprobado":
        cobro.estado_pago = "reportado"
        cobro.save()


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


def cita_lista_para_giro(cita):
    if cita is None or cita.estado_pago != "aprobado" or not cita.trabajo_realizado:
        return False
    try:
        return cita.comentario is not None
    except (ObjectDoesNotExist, Comentario.DoesNotExist):
        return False


def liberar_giro_si_realizado(cita):
    return intentar_giro_servicio(cita)


def intentar_giro_servicio(cita):
    """Anota el restante. El dinero se queda en Wompi hasta que ERA shop autorice el giro."""
    if not cita_lista_para_giro(cita):
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


def _avisar_consignar_servicio(cita, giro, creado):
    if not creado:
        return
    from django.contrib.auth.models import User
    from pedidos.avisos import dejar_aviso

    staff = list(User.objects.filter(is_staff=True, is_active=True)[:30])
    if not staff:
        return
    dejar_aviso(
        staff,
        f"Consignar oficio · Nequi {giro.destino_nequi or 'sin número'}",
        (
            f"{cita.oferente.nombre} ({cita.oferente.responsable}). "
            f"Cliente {cita.cliente_nombre} pagó ${cita.monto_cop}. "
            f"Comisión ERA shop ${cita.comision_cop}. Tarifa Wompi ${cita.tarifa_pasarela_cop}. "
            f"Transferir ${giro.monto_cop} al Nequi {giro.destino_nequi or 'sin número'}."
        ),
        "/servicios/admin-era/consignar/",
    )


def repartir_cita(cita):
    giro, creado = GiroCita.objects.get_or_create(
        cita=cita,
        defaults={
            "monto_cop": cita.neto_vendedor or 0,
            "comision_cop": cita.comision_cop or 0,
            "destino_nequi": (cita.oferente.nequi or "")[:20],
        },
    )
    if giro.estado in ("pagado", "enviado"):
        if creado:
            _avisar_consignar_servicio(cita, giro, creado)
        return giro
    giro.monto_cop = cita.neto_vendedor or 0
    giro.comision_cop = cita.comision_cop or 0
    giro.destino_nequi = (cita.oferente.nequi or "")[:20]
    if not giro.payout_id:
        giro.estado = "pendiente"
        giro.detalle = "El dinero sigue en Wompi. ERA shop autoriza el giro al Nequi del oferente."
        giro.save()
    _avisar_consignar_servicio(cita, giro, creado)
    return giro


def autorizar_giro_cita(cita):
    giro = GiroCita.objects.filter(cita=cita).first() or intentar_giro_servicio(cita)
    if giro is None or giro.estado in ("pagado", "enviado"):
        return giro
    giro.monto_cop = cita.neto_vendedor or giro.monto_cop
    giro.destino_nequi = (cita.oferente.nequi or giro.destino_nequi or "")[:20]
    giros_base._enviar(giro, cita.oferente, f"giro-srv-{cita.id}")
    return giro
