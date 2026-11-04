import json
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from productos.models import Producto
from vendedores.forms import _nequi_valido
from vendedores.opciones import TIPOS
from vendedores.services import aplicar_comision

from .avisos import avisar_estado, avisar_mensaje, avisar_pedido_nuevo
from .models import Calificacion, CuentaPlataforma, MensajePedido, Pedido, Reclamo
from .resumen import pdf_pedido
from .services import wompi


def _suma_comision(estado):
    valor = Pedido.objects.filter(estado_comision=estado).aggregate(s=Sum("comision_cop"))["s"]
    return valor or 0


def nequi_plataforma():
    cuenta = CuentaPlataforma.objects.order_by("id").first()
    if cuenta and cuenta.nequi:
        return cuenta.nequi, cuenta.titular or "ERA shop"
    return getattr(settings, "PAGO_NEQUI", "") or "", "ERA shop"


def lista_pedidos(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path(), login_url="/admin/login/")
    return _registro_ventas(request)


def _perfil_comprador(request):
    if not request.user.is_authenticated:
        return None
    from vendedores.models import ClienteTienda, Comprador
    try:
        persona = request.user.comprador
    except Comprador.DoesNotExist:
        persona = None
    if persona is not None:
        return {
            "comprador": persona,
            "cliente_tienda": None,
            "nombre": persona.nombre,
            "documento": persona.documento,
            "telefono": persona.telefono,
            "email": request.user.email,
            "direccion": persona.direccion,
            "barrio": persona.barrio,
            "ciudad": persona.ciudad,
            "departamento": persona.departamento,
            "referencia": persona.referencia,
        }
    try:
        tienda = request.user.cliente_tienda
    except ClienteTienda.DoesNotExist:
        tienda = None
    if tienda is None or not tienda.registro_completo():
        return None
    return {
        "comprador": None,
        "cliente_tienda": tienda,
        "nombre": tienda.responsable,
        "documento": tienda.documento,
        "telefono": tienda.telefono,
        "email": request.user.email,
        "direccion": tienda.direccion,
        "barrio": tienda.barrio,
        "ciudad": tienda.ciudad,
        "departamento": tienda.departamento,
        "referencia": tienda.referencia,
    }


def _marcar_contacto(request, pedido):
    ids = request.session.get("pedidos_contacto", [])
    if pedido.id not in ids:
        ids.append(pedido.id)
        request.session["pedidos_contacto"] = ids


def contacto_visible(request, pedido):
    """El teléfono del vendedor, mayorista o detallista, sale cuando la transferencia ya está aprobada."""
    if not pedido or not pedido.vendedor_id or pedido.estado_pago != "aprobado":
        return False
    if request.user.is_authenticated and request.user.is_staff:
        return True
    if request.user.is_authenticated:
        from vendedores.models import ClienteTienda, Comprador, Vendedor
        try:
            if request.user.vendedor.id == pedido.vendedor_id:
                return True
        except Vendedor.DoesNotExist:
            pass
        try:
            if pedido.cliente_tienda_id and request.user.cliente_tienda.id == pedido.cliente_tienda_id:
                return True
        except ClienteTienda.DoesNotExist:
            pass
        try:
            if pedido.comprador_id and request.user.comprador.id == pedido.comprador_id:
                return True
        except Comprador.DoesNotExist:
            pass
    clave = (request.GET.get("clave") or "").strip()
    if clave and clave == pedido.clave_contacto:
        _marcar_contacto(request, pedido)
        return True
    return pedido.id in request.session.get("pedidos_contacto", [])


def crear_pedido(request, producto_id):
    if request.method != "POST":
        return redirect("detalle_producto", producto_id)

    try:
        cantidad = int(request.POST.get("cantidad") or 1)
    except ValueError:
        cantidad = 1
    if cantidad < 1:
        cantidad = 1
    if cantidad > 999:
        cantidad = 999

    perfil = _perfil_comprador(request)

    with transaction.atomic():
        producto = get_object_or_404(
            Producto.objects.select_for_update(),
            pk=producto_id,
            activo=True,
        )
        if producto.vendedor_id and producto.vendedor.estado != "activo":
            raise Http404("Producto no disponible")

        def _error(msg):
            return render(request, "productos/detalle.html", {"producto": producto, "error": msg})

        if perfil is None:
            return _error("Regístrate con tus datos antes de pedir.")
        if producto.controla_stock and producto.stock < cantidad:
            return _error("No hay suficientes unidades.")

        precio = Decimal(producto.precio_vigente)
        es_mayor = False
        if producto.precio_mayor_cop and producto.vendedor_id and request.user.is_authenticated:
            from vendedores.models import ClienteTienda, Conexion
            try:
                cliente = request.user.cliente_tienda
            except ClienteTienda.DoesNotExist:
                cliente = None
            minimo = producto.cantidad_minima or 1
            if (
                cliente
                and cantidad >= minimo
                and Conexion.objects.filter(cliente=cliente, proveedor_id=producto.vendedor_id).exists()
            ):
                precio = Decimal(producto.precio_mayor_cop)
                es_mayor = True
            elif cantidad > 20:
                return _error("En mostrador el máximo por pedido es 20. El precio al por mayor aplica si tu tienda está conectada y pides el mínimo.")
        elif cantidad > 20:
            cantidad = 20
            precio = Decimal(producto.precio_vigente)
        modo = producto.modo_envio or ("incluido" if producto.envio_gratis else "aparte")
        envio = Decimal("0")
        if modo == "aparte":
            envio = Decimal(producto.costo_envio_cop or 0)
        subtotal = (precio * cantidad + envio).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP,
        )
        vendedor = producto.vendedor
        pedido = Pedido.objects.create(
            producto=producto,
            vendedor=vendedor,
            cliente_tienda=perfil.get("cliente_tienda"),
            comprador=perfil.get("comprador"),
            variante=request.POST.get("variante", ""),
            cantidad=cantidad,
            cliente_nombre=perfil["nombre"],
            cliente_telefono=perfil["telefono"],
            cliente_email=perfil["email"],
            cliente_direccion=perfil["direccion"],
            cliente_barrio=perfil["barrio"],
            cliente_ciudad=perfil["ciudad"],
            cliente_departamento=perfil["departamento"],
            cliente_documento=perfil["documento"],
            cliente_referencia=perfil["referencia"],
            modo_envio=modo,
            envio_cop=envio,
            monto_cop=subtotal,
            subtotal_cop=subtotal,
            es_mayor=es_mayor,
            estado="pendiente",
            estado_pago="pendiente",
            contacto_responsable=vendedor.responsable if vendedor else "",
            contacto_telefono=vendedor.telefono if vendedor else "",
            contacto_whatsapp=vendedor.whatsapp if vendedor else "",
            contacto_email=vendedor.user.email if vendedor else "",
            contacto_direccion=vendedor.direccion if vendedor else "",
            contacto_nequi=vendedor.nequi if vendedor else "",
            clave_contacto=uuid.uuid4().hex,
        )
        extra = (pedido.id % 89) + 1
        pedido.monto_cop = subtotal + extra
        pedido.referencia_pago = f"PED-{pedido.id}"
        aplicar_comision(pedido)
        pedido.save()
        MensajePedido.objects.create(
            pedido=pedido,
            autor="plataforma",
            nombre="ERA shop",
            texto=(
                "Pedido creado. El teléfono, WhatsApp, correo y dirección del vendedor "
                "aparecen en este pedido cuando la transferencia quede aprobada."
            ),
        )
        if producto.controla_stock:
            producto.stock -= cantidad
            producto.save(update_fields=["stock"])

    _marcar_contacto(request, pedido)
    avisar_pedido_nuevo(
        pedido,
        request.build_absolute_uri(f"/pedidos/{pedido.id}/?clave={pedido.clave_contacto}"),
        request.build_absolute_uri(f"/pedidos/{pedido.id}/"),
    )
    return redirect(f"/pedidos/pagar/{pedido.id}/?clave={pedido.clave_contacto}")


def pagar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if pedido.estado_pago == "aprobado":
        return render(request, "pedidos/gracias.html", {
            "pedido": pedido,
            "pagado": True,
            "contacto_visible": contacto_visible(request, pedido),
        })
    if request.method == "POST":
        ctx = _ctx_pago(pedido, request)
        ctx["contacto_visible"] = contacto_visible(request, pedido)
        ctx["error"] = "El pago no se anota a mano ni se gira por fuera. Se cobra en esta página."
        return render(request, "pedidos/pagar.html", ctx)
    ctx = _ctx_pago(pedido, request)
    ctx["contacto_visible"] = contacto_visible(request, pedido)
    return render(request, "pedidos/pagar.html", ctx)


def _ctx_pago(pedido, request=None):
    from django.urls import reverse

    from .services import wompi

    ctx = {
        "pedido": pedido,
        "tarjeta_lista": wompi.checkout_listo(),
    }
    if request is not None and ctx["tarjeta_lista"]:
        destino = request.build_absolute_uri(reverse("resultado_pago", args=[pedido.id]))
        if pedido.clave_contacto:
            destino = f"{destino}?clave={pedido.clave_contacto}"
        ctx["wompi"] = wompi.contexto_widget(pedido, destino)
    return ctx


def resultado_pago(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    tx_id = (request.GET.get("id") or "").strip()[:80]
    if tx_id:
        publica = wompi.claves_wompi()[0]
        tx = wompi.consultar_transaccion(tx_id, publica)
        mismo_pedido = tx and (tx.get("reference") or "") == pedido.referencia_pago
        mismo_valor = tx and int(tx.get("amount_in_cents") or 0) == wompi.monto_centavos(pedido)
        if mismo_pedido and mismo_valor:
            _aplicar_transaccion(pedido, tx)
            pedido.refresh_from_db()
    return render(
        request,
        "pedidos/gracias.html",
        {
            "pedido": pedido,
            "pagado": pedido.estado_pago == "aprobado",
            "reportado": pedido.estado_pago == "reportado",
            "esperando": pedido.estado_pago == "pendiente",
            "contacto_visible": contacto_visible(request, pedido),
        },
    )


@csrf_exempt
@require_POST
def wompi_evento(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("json")
    checksum = (payload.get("signature") or {}).get("checksum") or ""
    if not wompi.evento_valido(payload, checksum):
        return HttpResponseBadRequest("firma")
    tx = wompi.extraer_transaccion(payload)
    ref = (tx.get("reference") or "").strip()
    if not ref:
        return HttpResponse("ok")
    pedido = Pedido.objects.filter(referencia_pago=ref).first()
    if not pedido:
        return HttpResponse("ok")
    _aplicar_transaccion(pedido, tx)
    return HttpResponse("ok")


def _aplicar_transaccion(pedido, tx):
    status = (tx.get("status") or "").upper()
    pedido.wompi_id = tx.get("id") or pedido.wompi_id
    pedido.metodo_pago = tx.get("payment_method_type") or pedido.metodo_pago
    if status == "APPROVED":
        ya_pagado = pedido.estado_pago == "aprobado"
        pedido.estado_pago = "aprobado"
        if pedido.estado == "pendiente":
            pedido.estado = "pagado"
        pedido.save()
        from .services.pagos import registrar_pago
        registrar_pago(
            pedido, "aprobado", "wompi",
            metodo=pedido.metodo_pago, wompi_id=pedido.wompi_id,
        )
        from .services.giros import repartir
        repartir(pedido)
        if not ya_pagado:
            try:
                from productos.tasks import procesar_pedido
                procesar_pedido(pedido.id)
            except Exception as e:
                pedido.notas = f"Pagado. Error al comprar al proveedor: {e}"
                pedido.save(update_fields=["notas"])
    elif status in ("DECLINED", "VOIDED"):
        pedido.estado_pago = "declinado"
        pedido.save()
        from .services.pagos import registrar_pago
        registrar_pago(pedido, "declinado", "wompi", metodo=pedido.metodo_pago, wompi_id=pedido.wompi_id)
    elif status == "ERROR":
        pedido.estado_pago = "error"
        pedido.save()
        from .services.pagos import registrar_pago
        registrar_pago(pedido, "error", "wompi", metodo=pedido.metodo_pago, wompi_id=pedido.wompi_id)
    elif pedido.estado_pago != "aprobado":
        pedido.estado_pago = "reportado"
        pedido.save()
        from .services.pagos import registrar_pago
        registrar_pago(
            pedido, "reportado", "wompi",
            metodo=pedido.metodo_pago, wompi_id=pedido.wompi_id,
        )
    else:
        pedido.save()


def _rol_pedido(request, pedido):
    if request.user.is_authenticated and request.user.is_staff:
        return "plataforma"
    if request.user.is_authenticated:
        from vendedores.models import ClienteTienda, Vendedor
        try:
            if request.user.vendedor.id == pedido.vendedor_id:
                return "vendedor"
        except Vendedor.DoesNotExist:
            pass
        try:
            if request.user.cliente_tienda.id == pedido.cliente_tienda_id:
                return "cliente"
        except ClienteTienda.DoesNotExist:
            pass
    if contacto_visible(request, pedido):
        return "cliente"
    return None


def _paso_pedido(estado):
    return {
        "pendiente": 0,
        "pagado": 1,
        "comprado": 1,
        "en_casillero": 1,
        "empacado": 2,
        "enviado": 3,
        "entregado": 4,
        "fallido": -1,
    }.get(estado, 0)


def _enlaces_pedido(request, pedido):
    cliente = request.build_absolute_uri(f"/pedidos/{pedido.id}/?clave={pedido.clave_contacto}")
    tienda = request.build_absolute_uri(f"/pedidos/{pedido.id}/")
    return cliente, tienda


def _nombre_autor(pedido, rol):
    if rol == "vendedor" and pedido.vendedor_id:
        return pedido.vendedor.nombre_tienda
    if rol == "plataforma":
        return "ERA shop"
    return pedido.cliente_nombre


def conversacion_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_related("producto", "vendedor", "cliente_tienda", "giro"),
        pk=pedido_id,
    )
    rol = _rol_pedido(request, pedido)
    if rol is None:
        raise Http404("Pedido no disponible")
    if getattr(pedido, "giro", None) and pedido.giro.estado == "enviado":
        from .services.giros import actualizar
        actualizar(pedido.giro)
    if request.method == "POST":
        accion = request.POST.get("accion") or "mensaje"
        if accion in ("pagado", "empacado", "enviado", "entregado"):
            _marcar_estado(request, pedido, rol, accion)
        elif accion == "calificar":
            _calificar(request, pedido, rol)
        elif accion == "reclamo":
            _abrir_reclamo(request, pedido, rol)
        elif accion == "resolver":
            _resolver_reclamo(request, pedido, rol)
        else:
            _publicar_mensaje(request, pedido, rol)
        return redirect(request.get_full_path())
    try:
        calificacion = pedido.calificacion
    except Calificacion.DoesNotExist:
        calificacion = None
    abierto = pedido.reclamos.filter(estado="abierto").first()
    return render(request, "pedidos/conversacion.html", {
        "pedido": pedido,
        "mensajes": pedido.mensajes.all(),
        "rol": rol,
        "calificacion": calificacion,
        "reclamo": abierto,
        "reclamos": pedido.reclamos.all(),
        "dias_reclamo": settings.DIAS_RECLAMO,
        "puede_devolver": _puede_devolver(pedido),
        "contacto_visible": contacto_visible(request, pedido),
    })


def resumen_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_related("producto", "vendedor"),
        pk=pedido_id,
    )
    if _rol_pedido(request, pedido) is None:
        raise Http404("Pedido no disponible")
    archivo = pdf_pedido(pedido)
    respuesta = HttpResponse(archivo, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="pedido-{pedido.id}.pdf"'
    return respuesta


def bodega_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_related("producto", "vendedor").prefetch_related("lineas__producto"),
        pk=pedido_id,
    )
    if _rol_pedido(request, pedido) is None or not pedido.es_mayor:
        raise Http404("Pedido no disponible")
    from .bodega import docx_bodega

    archivo = docx_bodega(pedido)
    respuesta = HttpResponse(
        archivo,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    respuesta["Content-Disposition"] = f'attachment; filename="pedido-{pedido.id}-bodega.docx"'
    return respuesta


def _publicar_mensaje(request, pedido, rol):
    texto = (request.POST.get("texto") or "").strip()
    if not texto:
        messages.error(request, "Escribe el mensaje.")
        return
    if len(texto) > 2000:
        messages.error(request, "El mensaje es demasiado largo.")
        return
    MensajePedido.objects.create(
        pedido=pedido, autor=rol, nombre=_nombre_autor(pedido, rol), texto=texto,
    )
    cliente, tienda = _enlaces_pedido(request, pedido)
    avisar_mensaje(pedido, rol, cliente, tienda)


def _datos_despacho(request, pedido):
    from datetime import datetime
    transportadora = (request.POST.get("transportadora") or "").strip()[:120]
    guia = (request.POST.get("guia") or "").strip()[:200]
    recibe = (request.POST.get("recibe_nombre") or pedido.cliente_nombre).strip()[:200]
    documento = "".join(ch for ch in (request.POST.get("recibe_documento") or "") if ch.isdigit())[:40]
    telefono = (request.POST.get("recibe_telefono") or "").strip()[:50]
    detalle = (request.POST.get("detalle_envio") or "").strip()[:300]
    try:
        fecha = datetime.strptime((request.POST.get("fecha_despacho") or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        fecha = None
    if not all([transportadora, guia, recibe, telefono]) or len(documento) < 5 or fecha is None:
        messages.error(
            request,
            "Para despachar escribe transportadora, guía, fecha, quién recibe, cédula y teléfono.",
        )
        return None
    return {
        "transportadora": transportadora,
        "guia": guia,
        "recibe": recibe,
        "documento": documento,
        "telefono": telefono,
        "detalle": detalle,
        "fecha": fecha,
    }


def _marcar_estado(request, pedido, rol, accion):
    if rol not in ("vendedor", "plataforma"):
        messages.error(request, "Solo la tienda actualiza el estado del pedido.")
        return
    if pedido.estado == "fallido":
        messages.error(request, "Ese pedido está cerrado.")
        return
    paso = _paso_pedido(pedido.estado)
    if accion == "pagado":
        messages.error(request, "El pago lo confirma la página. No se marca a mano.")
        return
    elif accion == "empacado" and paso == 1:
        pedido.estado = "empacado"
        pedido.save(update_fields=["estado"])
        nota = "La tienda empacó el pedido."
    elif accion == "enviado" and paso == 2:
        datos = _datos_despacho(request, pedido)
        if datos is None:
            return
        pedido.estado = "enviado"
        pedido.tracking = datos["guia"]
        pedido.transportadora = datos["transportadora"]
        pedido.fecha_despacho = datos["fecha"]
        pedido.recibe_nombre = datos["recibe"]
        pedido.recibe_documento = datos["documento"]
        pedido.recibe_telefono = datos["telefono"]
        pedido.detalle_envio = datos["detalle"]
        pedido.save(update_fields=[
            "estado", "tracking", "transportadora", "fecha_despacho",
            "recibe_nombre", "recibe_documento", "recibe_telefono", "detalle_envio",
        ])
        nota = (
            f"Despachado el {datos['fecha']:%d/%m/%Y} por {datos['transportadora']}. "
            f"Guía {datos['guia']}. Recibe {datos['recibe']}, cédula {datos['documento']}, "
            f"teléfono {datos['telefono']}."
        )
        if datos["detalle"]:
            nota += f" {datos['detalle']}"
    elif accion == "entregado" and paso == 3:
        recibio = (request.POST.get("entrega_recibio") or "").strip()[:200]
        documento = "".join(ch for ch in (request.POST.get("entrega_documento") or "") if ch.isdigit())[:40]
        nota_entrega = (request.POST.get("entrega_nota") or "").strip()[:300]
        if not recibio or len(documento) < 5:
            messages.error(request, "Escribe quién recibió el pedido y su cédula.")
            return
        pedido.estado = "entregado"
        pedido.entregado_en = timezone.now()
        pedido.entrega_recibio = recibio
        pedido.entrega_documento = documento
        pedido.entrega_nota = nota_entrega
        pedido.save(update_fields=[
            "estado", "entregado_en", "entrega_recibio", "entrega_documento", "entrega_nota",
        ])
        nota = (
            f"Entregado el {timezone.localtime(pedido.entregado_en):%d/%m/%Y %H:%M} "
            f"a {recibio}, cédula {documento}."
        )
        if nota_entrega:
            nota += f" {nota_entrega}"
        nota += " Tienes 5 días para una devolución y para calificar."
    else:
        messages.error(request, "Ese paso no corresponde al estado actual del pedido.")
        return
    MensajePedido.objects.create(pedido=pedido, autor="plataforma", nombre="ERA shop", texto=nota)
    cliente, _tienda = _enlaces_pedido(request, pedido)
    avisar_estado(pedido, nota, cliente)
    messages.success(request, nota)


def _calificar(request, pedido, rol):
    if rol != "cliente":
        messages.error(request, "Califica quien hizo el pedido.")
        return
    if pedido.estado != "entregado" or not pedido.vendedor_id:
        messages.error(request, "La calificación se abre cuando el pedido está entregado.")
        return
    if Calificacion.objects.filter(pedido=pedido).exists():
        messages.error(request, "Este pedido ya tiene calificación.")
        return
    try:
        estrellas = int(request.POST.get("estrellas") or 0)
    except ValueError:
        estrellas = 0
    if estrellas < 1 or estrellas > 5:
        messages.error(request, "Elige de 1 a 5 estrellas.")
        return
    comentario = (request.POST.get("comentario") or "").strip()[:500]
    Calificacion.objects.create(
        pedido=pedido, vendedor=pedido.vendedor, estrellas=estrellas, comentario=comentario,
    )
    messages.success(request, "Calificación guardada.")


def _puede_devolver(pedido):
    if pedido.estado != "entregado" or not pedido.entregado_en:
        return False
    if pedido.reclamos.filter(estado="abierto").exists():
        return False
    return timezone.now() <= pedido.entregado_en + timedelta(days=settings.DIAS_RECLAMO)


def _abrir_reclamo(request, pedido, rol):
    if rol != "cliente":
        messages.error(request, "El reclamo lo abre quien hizo el pedido.")
        return
    if pedido.reclamos.filter(estado="abierto").exists():
        messages.error(request, "Ya hay un reclamo abierto en este pedido.")
        return
    tipo = request.POST.get("tipo") or "reclamo"
    if tipo not in ("reclamo", "devolucion"):
        tipo = "reclamo"
    motivo = (request.POST.get("motivo") or "").strip()
    if len(motivo) < 20:
        messages.error(request, "Cuenta el reclamo con al menos 20 caracteres.")
        return
    if tipo == "devolucion" and not _puede_devolver(pedido):
        messages.error(request, f"La devolución solo está abierta {settings.DIAS_RECLAMO} días después de la entrega.")
        return
    if pedido.estado == "fallido":
        messages.error(request, "Ese pedido está cerrado.")
        return
    limite = timezone.now() + timedelta(days=settings.DIAS_RECLAMO)
    Reclamo.objects.create(pedido=pedido, tipo=tipo, motivo=motivo[:2000], fecha_limite=limite)
    texto = f"Se abrió un {('reclamo' if tipo == 'reclamo' else 'solicitud de devolución')}. La tienda tiene {settings.DIAS_RECLAMO} días para responder aquí."
    MensajePedido.objects.create(pedido=pedido, autor="plataforma", nombre="ERA shop", texto=texto)
    cliente, tienda = _enlaces_pedido(request, pedido)
    avisar_mensaje(pedido, "cliente", cliente, tienda)
    messages.success(request, "Quedó abierto en el pedido.")


def _resolver_reclamo(request, pedido, rol):
    if rol not in ("vendedor", "plataforma"):
        messages.error(request, "La tienda responde el reclamo.")
        return
    reclamo = pedido.reclamos.filter(estado="abierto").first()
    if reclamo is None:
        messages.error(request, "No hay un reclamo abierto.")
        return
    decision = request.POST.get("decision") or ""
    if decision not in ("aceptado", "rechazado", "cerrado"):
        messages.error(request, "Elige si lo aceptas, lo rechazas o lo cierras.")
        return
    reclamo.estado = decision
    reclamo.save(update_fields=["estado"])
    nota = f"La tienda marcó el {reclamo.get_tipo_display().lower()} como {reclamo.get_estado_display().lower()}."
    MensajePedido.objects.create(pedido=pedido, autor="plataforma", nombre="ERA shop", texto=nota)
    cliente, _tienda = _enlaces_pedido(request, pedido)
    avisar_estado(pedido, nota, cliente)
    messages.success(request, nota)


def _porcentaje(valor):
    numero = _decimal_get(valor)
    if numero is None or numero < 0 or numero > 100:
        return None
    return numero.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_get(valor):
    try:
        return Decimal(str(valor).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _registro_ventas(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "nequi":
            try:
                numero = _nequi_valido(request.POST.get("nequi") or "")
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                cuenta, _ = CuentaPlataforma.objects.get_or_create(pk=1)
                cuenta.nequi = numero
                cuenta.titular = (request.POST.get("titular") or "ERA shop").strip()[:120]
                cuenta.save()
                messages.success(request, "Nequi de comisiones guardado. Los vendedores lo ven al liquidar.")
        elif accion == "wompi":
            cuenta, _ = CuentaPlataforma.objects.get_or_create(pk=1)
            publica = (request.POST.get("wompi_publica") or "").strip()
            integridad = (request.POST.get("wompi_integridad") or "").strip()
            eventos = (request.POST.get("wompi_eventos") or "").strip()
            if publica:
                cuenta.wompi_publica = publica[:200]
            if integridad:
                cuenta.wompi_integridad = integridad[:200]
            if eventos:
                cuenta.wompi_eventos = eventos[:200]
            if not (publica or integridad or eventos):
                messages.error(request, "Pega al menos la llave pública de Wompi.")
            else:
                cuenta.save()
                messages.success(request, "Wompi guardado. El botón de pago ya puede cobrar.")
        elif accion == "porcentajes":
            detalle = _porcentaje(request.POST.get("detalle"))
            mayor = _porcentaje(request.POST.get("mayor"))
            if detalle is None or mayor is None:
                messages.error(request, "Escribe cada porcentaje entre 0 y 100.")
            else:
                cuenta, _creada = CuentaPlataforma.objects.get_or_create(pk=1)
                cuenta.comision_detalle_pct = detalle
                cuenta.comision_mayor_pct = mayor
                cuenta.save(update_fields=["comision_detalle_pct", "comision_mayor_pct"])
                messages.success(
                    request,
                    "Porcentajes guardados. Las ventas nuevas, la calculadora y el pedido del establecimiento usan estos valores.",
                )
        elif accion == "payouts":
            cuenta, _ = CuentaPlataforma.objects.get_or_create(pk=1)
            api_key = (request.POST.get("payouts_api_key") or "").strip()
            user_id = (request.POST.get("payouts_user_id") or "").strip()
            if api_key:
                cuenta.payouts_api_key = api_key[:200]
            if user_id:
                cuenta.payouts_user_id = user_id[:80]
            if not (api_key or user_id):
                messages.error(request, "Pega la API Key y el ID de usuario de Pagos a terceros.")
            else:
                cuenta.save()
                from .services.giros import reintentar_pendientes
                reintentar_pendientes()
                messages.success(request, "Pagos a terceros guardado. Los giros pendientes se vuelven a intentar.")
        elif accion == "pagar_vendedor":
            pedido = get_object_or_404(Pedido, pk=request.POST.get("pedido") or 0)
            from .services.giros import marcar_pago_manual
            giro = marcar_pago_manual(pedido, (request.POST.get("comprobante") or "").strip()[:120])
            if giro and giro.estado == "pagado":
                messages.success(request, f"Quedó registrado el pago del restante del pedido #{pedido.id}.")
            else:
                messages.error(request, "Ese pedido todavía no tiene un pago confirmado para consignar.")
        else:
            pedido = get_object_or_404(Pedido, pk=request.POST.get("pedido") or 0)
            if accion == "confirmar" and pedido.estado_comision in ("pendiente", "reportada"):
                pedido.estado_comision = "pagada"
                pedido.comision_pagada_en = timezone.now()
                pedido.save(update_fields=["estado_comision", "comision_pagada_en"])
                messages.success(request, f"Comisión del pedido #{pedido.id} confirmada.")
            elif accion == "rechazar" and pedido.estado_comision == "reportada":
                pedido.estado_comision = "pendiente"
                pedido.fecha_limite_comision = timezone.now() + timedelta(days=2)
                pedido.comprobante_comision = ""
                pedido.comprobante_url = ""
                pedido.comprobante_ruta = ""
                pedido.save(update_fields=[
                    "estado_comision", "fecha_limite_comision",
                    "comprobante_comision", "comprobante_url", "comprobante_ruta",
                ])
                messages.error(request, f"Comprobante del pedido #{pedido.id} rechazado. Tienen 2 días.")
        cola = request.GET.urlencode()
        return redirect(request.path + (f"?{cola}" if cola else ""))

    qs = Pedido.objects.select_related("producto", "vendedor", "cliente_tienda", "pago", "giro").prefetch_related("lineas")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(cliente_nombre__icontains=q)
            | Q(cliente_telefono__icontains=q)
            | Q(cliente_email__icontains=q)
            | Q(cliente_ciudad__icontains=q)
            | Q(cliente_direccion__icontains=q)
            | Q(cliente_documento__icontains=q)
            | Q(transportadora__icontains=q)
            | Q(tracking__icontains=q)
            | Q(referencia_pago__icontains=q)
            | Q(producto__titulo__icontains=q)
            | Q(vendedor__nombre_tienda__icontains=q)
            | Q(vendedor__ciudad__icontains=q)
            | Q(vendedor__responsable__icontains=q)
            | Q(vendedor__documento__icontains=q)
            | Q(comprobante__icontains=q)
            | Q(comprobante_comision__icontains=q)
        )
        if q.isdigit():
            qs = qs | Pedido.objects.filter(pk=int(q))
    tipo = request.GET.get("tipo") or ""
    if tipo == "minorista":
        qs = qs.exclude(vendedor__tipo__in=("mayorista", "importador"))
    elif tipo:
        qs = qs.filter(vendedor__tipo=tipo)
    for campo, nombre in (
        ("estado", "estado"),
        ("estado_pago", "pago"),
        ("estado_comision", "comision"),
    ):
        valor = request.GET.get(nombre) or ""
        if valor:
            qs = qs.filter(**{campo: valor})
    ciudad = (request.GET.get("ciudad") or "").strip()
    if ciudad:
        qs = qs.filter(Q(cliente_ciudad__icontains=ciudad) | Q(vendedor__ciudad__icontains=ciudad))
    desde = request.GET.get("desde") or ""
    hasta = request.GET.get("hasta") or ""
    if desde:
        qs = qs.filter(creado__date__gte=desde)
    if hasta:
        qs = qs.filter(creado__date__lte=hasta)
    minimo = _decimal_get(request.GET.get("monto_min"))
    maximo = _decimal_get(request.GET.get("monto_max"))
    if minimo is not None:
        qs = qs.filter(monto_cop__gte=minimo)
    if maximo is not None:
        qs = qs.filter(monto_cop__lte=maximo)
    if request.GET.get("con_comprobante") == "1":
        qs = qs.exclude(comprobante_url="")

    totales = qs.aggregate(
        ventas=Count("id"),
        unidades=Sum("cantidad"),
        dinero=Sum("monto_cop"),
        comision=Sum("comision_cop"),
    )
    deben = qs.filter(estado_comision__in=["pendiente", "vencida"]).aggregate(s=Sum("comision_cop"))["s"] or 0
    reportado = qs.filter(estado_comision="reportada").aggregate(s=Sum("comision_cop"))["s"] or 0
    pagado = qs.filter(estado_comision="pagada").aggregate(s=Sum("comision_cop"))["s"] or 0
    pagina = Paginator(qs.distinct(), 40).get_page(request.GET.get("p"))
    nequi, titular = nequi_plataforma()
    por_pagar = (
        Pedido.objects.filter(estado_pago="aprobado", vendedor__isnull=False)
        .filter(Q(giro__isnull=True) | Q(giro__estado__in=["pendiente", "sin_datos", "enviado", "rechazado"]))
        .select_related("vendedor", "producto", "giro")
        .prefetch_related("lineas")
        .order_by("-creado")[:40]
    )
    return render(request, "pedidos/lista.html", {
        "pedidos": pagina,
        "pagina": pagina,
        "totales": totales,
        "deben": deben,
        "reportado": reportado,
        "pagado": pagado,
        "tipos": TIPOS,
        "estados": Pedido.ESTADOS,
        "pagos": Pedido.ESTADOS_PAGO,
        "comisiones": Pedido.ESTADOS_COMISION,
        "nequi": nequi,
        "titular": titular,
        "wompi_conectado": wompi.checkout_listo(),
        "webhook_url": request.build_absolute_uri("/pedidos/wompi/evento/"),
        "por_pagar": por_pagar,
        "q": q,
    })
