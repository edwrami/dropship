from django.conf import settings
from django.core.mail import send_mail


def avisar(asunto, cuerpo, destinatarios):
    limpios = []
    for correo in destinatarios:
        correo = (correo or "").strip()
        if correo and correo.lower() not in {c.lower() for c in limpios}:
            limpios.append(correo)
    if not limpios:
        return
    try:
        send_mail(
            asunto,
            cuerpo,
            getattr(settings, "DEFAULT_FROM_EMAIL", "ERA shop <no-responder@era.shop>"),
            limpios,
            fail_silently=True,
        )
    except Exception:
        return


def _correos(usuarios):
    vistos = set()
    for user in usuarios:
        correo = (getattr(user, "email", "") or "").strip().lower()
        if correo:
            vistos.add(correo)
    return vistos


def dejar_aviso(usuarios, asunto, cuerpo, url=""):
    from .models import Aviso

    vistos = set()
    correos = []
    for user in usuarios:
        if user is None or not getattr(user, "pk", None) or user.pk in vistos:
            continue
        vistos.add(user.pk)
        try:
            Aviso.objects.create(
                user=user,
                titulo=(asunto or "ERA shop")[:160],
                texto=(cuerpo or "")[:2000],
                url=(url or "")[:300],
            )
        except Exception:
            continue
        if user.email:
            correos.append(user.email)
    avisar(asunto, cuerpo, correos)


def _partes(pedido):
    compradores = []
    vendedores = []
    if pedido.comprador_id:
        compradores.append(pedido.comprador.user)
    if pedido.cliente_tienda_id:
        compradores.append(pedido.cliente_tienda.user)
    if pedido.vendedor_id:
        vendedores.append(pedido.vendedor.user)
    return compradores, vendedores


def _avisar_y_correo(usuarios, asunto, cuerpo, url, correos_extra):
    if url and url not in (cuerpo or ""):
        cuerpo = f"{cuerpo}\n{url}"
    dejar_aviso(usuarios, asunto, cuerpo, url)
    ya = _correos(usuarios)
    pendientes = []
    for correo in correos_extra:
        limpio = (correo or "").strip()
        if limpio and limpio.lower() not in ya:
            pendientes.append(limpio)
    avisar(asunto, cuerpo, pendientes)


def avisar_pedido_nuevo(pedido, enlace_cliente, enlace_tienda):
    compradores, vendedores = _partes(pedido)
    tienda = (
        f"{pedido.cliente_nombre} pidió {pedido.producto.titulo}, "
        f"{pedido.cantidad} und., ${pedido.monto_cop} COP."
    )
    _avisar_y_correo(
        vendedores,
        f"Nuevo pedido #{pedido.id} · ERA shop",
        tienda + "\nAbre el pedido y responde ahí.",
        enlace_tienda,
        [pedido.contacto_email],
    )
    _avisar_y_correo(
        compradores,
        f"Tu pedido #{pedido.id} · ERA shop",
        (
            f"Quedó creado: {pedido.producto.titulo}, {pedido.cantidad} und., "
            f"${pedido.monto_cop} COP."
        ),
        enlace_cliente,
        [pedido.cliente_email],
    )


def avisar_mensaje(pedido, autor, enlace_cliente, enlace_tienda):
    compradores, vendedores = _partes(pedido)
    if autor == "cliente":
        _avisar_y_correo(
            vendedores,
            f"Mensaje en el pedido #{pedido.id} · ERA shop",
            f"{pedido.cliente_nombre} escribió en el pedido.",
            enlace_tienda,
            [pedido.contacto_email],
        )
    elif autor == "vendedor":
        _avisar_y_correo(
            compradores,
            f"La tienda escribió en tu pedido #{pedido.id} · ERA shop",
            "Entra a la conversación.",
            enlace_cliente,
            [pedido.cliente_email],
        )


def avisar_estado(pedido, texto, enlace_cliente):
    compradores, _vendedores = _partes(pedido)
    _avisar_y_correo(
        compradores,
        f"Pedido #{pedido.id} · ERA shop",
        texto,
        enlace_cliente,
        [pedido.cliente_email],
    )


def avisar_pago(pedido):
    from django.contrib.auth.models import User

    tienda = pedido.vendedor.nombre_tienda if pedido.vendedor_id else "ERA shop"
    ruta = f"/pedidos/{pedido.id}/"
    compradores, vendedores = _partes(pedido)
    _avisar_y_correo(
        compradores,
        f"Pago aprobado · pedido #{pedido.id}",
        (
            f"Tu pago del pedido #{pedido.id} quedó aprobado: ${pedido.monto_cop} COP. "
            f"Tienda: {tienda}. El comprobante está en el pedido."
        ),
        ruta,
        [pedido.cliente_email],
    )
    _avisar_y_correo(
        vendedores,
        f"Pago recibido · pedido #{pedido.id}",
        (
            f"Entró el pago del pedido #{pedido.id} de {pedido.cliente_nombre}: "
            f"${pedido.monto_cop} COP. El restante se consigna desde ERA shop."
        ),
        ruta,
        [pedido.contacto_email],
    )
    staff = list(User.objects.filter(is_staff=True, is_active=True))
    dejar_aviso(
        staff,
        f"Entró un pago · pedido #{pedido.id}",
        (
            f"{pedido.cliente_nombre} pagó ${pedido.monto_cop} COP. "
            "En Ventas queda lo que le debes a cada vendedor."
        ),
        "/pedidos/",
    )


def avisar_stock_bajo(producto):
    if not producto.controla_stock or not producto.vendedor_id or producto.stock > 5:
        return
    from .models import Aviso

    vendedor = producto.vendedor
    titulo = f"Quedan {producto.stock} de {producto.titulo[:90]}"
    if Aviso.objects.filter(user_id=vendedor.user_id, titulo=titulo, leido=False).exists():
        return
    dejar_aviso(
        [vendedor.user],
        titulo,
        f"{producto.titulo} quedó con {producto.stock} unidades.",
        f"/vendedores/producto/{producto.id}/editar/",
    )
