from django.conf import settings
from django.core.mail import send_mail


def avisar(asunto, cuerpo, destinatarios):
    limpios = []
    for correo in destinatarios:
        correo = (correo or "").strip()
        if correo and correo not in limpios:
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


def avisar_pedido_nuevo(pedido, enlace_cliente, enlace_tienda):
    avisar(
        f"Nuevo pedido #{pedido.id} · ERA shop",
        (
            f"{pedido.cliente_nombre} pidió {pedido.producto.titulo}, "
            f"{pedido.cantidad} und., ${pedido.monto_cop} COP.\n"
            f"Abre el pedido y responde ahí:\n{enlace_tienda}"
        ),
        [pedido.contacto_email],
    )
    avisar(
        f"Tu pedido #{pedido.id} · ERA shop",
        (
            f"Quedó creado: {pedido.producto.titulo}, {pedido.cantidad} und., "
            f"${pedido.monto_cop} COP.\n"
            f"Habla con la tienda en este enlace:\n{enlace_cliente}"
        ),
        [pedido.cliente_email],
    )


def avisar_mensaje(pedido, autor, enlace_cliente, enlace_tienda):
    if autor == "cliente":
        avisar(
            f"Mensaje en el pedido #{pedido.id} · ERA shop",
            f"{pedido.cliente_nombre} escribió en el pedido. Responde aquí:\n{enlace_tienda}",
            [pedido.contacto_email],
        )
    elif autor == "vendedor":
        avisar(
            f"La tienda escribió en tu pedido #{pedido.id} · ERA shop",
            f"Entra a la conversación:\n{enlace_cliente}",
            [pedido.cliente_email],
        )


def avisar_estado(pedido, texto, enlace_cliente):
    avisar(
        f"Pedido #{pedido.id} · {texto}",
        f"{texto}.\nSigue el pedido aquí:\n{enlace_cliente}",
        [pedido.cliente_email],
    )
