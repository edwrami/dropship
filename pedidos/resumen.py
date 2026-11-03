def _esc(texto):
    return (
        str(texto)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def pdf_pedido(pedido):
    lineas = [
        "ERA shop",
        f"Resumen del pedido #{pedido.id}",
        f"Referencia: {pedido.referencia_pago}",
        f"Fecha: {pedido.creado:%d/%m/%Y %H:%M}",
        f"Producto: {pedido.producto.titulo[:80]}",
        f"Cantidad: {pedido.cantidad}",
        f"Total: ${pedido.monto_cop} COP",
        f"Pago: {pedido.get_estado_pago_display}",
        f"Estado: {pedido.get_estado_display}",
    ]
    pago = getattr(pedido, "pago", None)
    if pago:
        lineas.append(f"Registro: {pago.get_estado_display} · {pago.metodo or 'sin medio'}")
        if pago.destino_nequi:
            lineas.append(f"Nequi destino: {pago.destino_nequi}")
        if pago.comprobante:
            lineas.append(f"Comprobante: {pago.comprobante}")
        if pago.wompi_id:
            lineas.append(f"Wompi: {pago.wompi_id}")
    giro = getattr(pedido, "giro", None)
    if giro:
        lineas.append(f"Comision ERA shop: ${giro.comision_cop}")
        lineas.append(f"Para la tienda: ${giro.monto_cop} · {giro.get_estado_display()}")
        if giro.destino_nequi:
            lineas.append(f"Nequi de la tienda: {giro.destino_nequi}")
    if pedido.tracking:
        lineas.append(f"Guia: {pedido.tracking}")
    if pedido.vendedor_id:
        lineas.append(f"Tienda: {pedido.vendedor.nombre_tienda} · {pedido.vendedor.ciudad}")
    lineas.append(f"Cliente: {pedido.cliente_nombre}")
    lineas.append(f"Entrega: {pedido.cliente_direccion[:90]}")
    lineas.append(pedido.cliente_ciudad)
    if pedido.variante:
        lineas.append(f"Variante: {pedido.variante[:80]}")
    lineas.append("La conversacion del pedido es el canal con la tienda.")

    comandos = ["BT", "/F1 11 Tf", "50 800 Td", "16 TL"]
    for linea in lineas:
        comandos.append(f"({_esc(linea)}) '")
    comandos.append("ET")
    stream = "\n".join(comandos).encode("latin-1", "replace")

    objetos = []
    objetos.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objetos.append(b"2 0 obj<< /Type /Pages /Count 1 /Kids [3 0 R] >>endobj\n")
    objetos.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objetos.append(
        b"4 0 obj<< /Length " + str(len(stream)).encode() + b" >>stream\n" + stream + b"\nendstream\nendobj\n"
    )
    objetos.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    salida = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for objeto in objetos:
        offsets.append(len(salida))
        salida.extend(objeto)
    inicio = len(salida)
    salida.extend(f"xref\n0 {len(offsets)}\n".encode())
    salida.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        salida.extend(f"{offset:010d} 00000 n \n".encode())
    salida.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{inicio}\n%%EOF".encode()
    )
    return bytes(salida)
