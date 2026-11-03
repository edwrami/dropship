from pedidos.models import MensajePedido, Pago


def registrar_pago(pedido, estado, origen, metodo="", comprobante="", wompi_id=""):
    """Deja constancia del pago en la base y en la conversación del pedido."""
    metodo = (metodo or pedido.metodo_pago or "pagina")[:40]
    comprobante = (comprobante or "")[:120]
    wompi_id = (wompi_id or pedido.wompi_id or "")[:80]
    destino = "" if origen == "wompi" else (pedido.contacto_nequi or "")[:20]
    pago, creado = Pago.objects.get_or_create(
        pedido=pedido,
        defaults={
            "monto_cop": pedido.monto_cop,
            "metodo": metodo,
            "estado": estado,
            "referencia": pedido.referencia_pago or "",
            "comprobante": comprobante,
            "destino_nequi": destino,
            "wompi_id": wompi_id,
            "origen": origen[:20],
        },
    )
    cambio = (
        creado
        or pago.estado != estado
        or (comprobante and pago.comprobante != comprobante)
        or (wompi_id and pago.wompi_id != wompi_id)
    )
    pago.monto_cop = pedido.monto_cop
    pago.metodo = metodo
    pago.estado = estado
    pago.referencia = pedido.referencia_pago or pago.referencia
    pago.comprobante = comprobante
    pago.destino_nequi = destino if origen == "wompi" else (destino or pago.destino_nequi)
    pago.wompi_id = wompi_id
    pago.origen = origen[:20]
    pago.save()
    if cambio:
        destino_txt = f" al Nequi {destino}" if destino else ""
        recibo = f", comprobante {comprobante}" if comprobante else ""
        MensajePedido.objects.create(
            pedido=pedido,
            autor="plataforma",
            nombre="ERA shop",
            texto=(
                f"Pago registrado{destino_txt}: ${pedido.monto_cop} COP "
                f"por {metodo}{recibo}. Estado: {pago.get_estado_display()}. "
                f"Referencia {pedido.referencia_pago}."
            ),
        )
    return pago
