from decimal import Decimal
from io import BytesIO

from docx import Document
from docx.shared import Cm, Pt


def _pesos(valor):
    numero = int(Decimal(str(valor or 0)))
    return "$" + f"{numero:,}".replace(",", ".")


def docx_bodega(pedido):
    documento = Document()
    estilo = documento.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(11)

    titulo = documento.add_heading(f"Pedido para bodega #{pedido.id}", level=1)
    titulo.alignment = 0
    documento.add_paragraph(f"Referencia {pedido.referencia_pago} · {pedido.creado:%d/%m/%Y %H:%M}")
    documento.add_paragraph("ERA shop · pasar este pedido a bodega")

    documento.add_heading("Establecimiento", level=2)
    documento.add_paragraph(pedido.cliente_nombre or "")
    if pedido.cliente_documento:
        documento.add_paragraph(f"Cédula o NIT: {pedido.cliente_documento}")
    documento.add_paragraph(f"Teléfono: {pedido.cliente_telefono}")
    if pedido.cliente_email:
        documento.add_paragraph(f"Correo: {pedido.cliente_email}")
    direccion = pedido.cliente_direccion or ""
    if pedido.cliente_barrio:
        direccion = f"{direccion}, {pedido.cliente_barrio}"
    documento.add_paragraph(f"Entrega: {direccion}")
    ciudad = pedido.cliente_ciudad or ""
    if pedido.cliente_departamento:
        ciudad = f"{ciudad}, {pedido.cliente_departamento}"
    documento.add_paragraph(ciudad)
    if pedido.cliente_referencia:
        documento.add_paragraph(f"Referencia: {pedido.cliente_referencia}")

    if pedido.vendedor_id:
        documento.add_heading("Proveedor", level=2)
        documento.add_paragraph(f"{pedido.vendedor.nombre_tienda} · {pedido.vendedor.ciudad}")

    documento.add_heading("Productos", level=2)
    tabla = documento.add_table(rows=1, cols=5)
    tabla.style = "Table Grid"
    tabla.autofit = True
    for celda, texto in zip(tabla.rows[0].cells, ("Producto", "Ficha", "Cantidad", "Precio", "Suma")):
        celda.text = texto
        for parrafo in celda.paragraphs:
            for run in parrafo.runs:
                run.bold = True

    lineas = list(pedido.lineas.select_related("producto"))
    if lineas:
        for linea in lineas:
            producto = linea.producto
            ficha = _ficha(producto, linea)
            fila = tabla.add_row().cells
            fila[0].text = linea.titulo
            fila[1].text = ficha
            fila[2].text = str(linea.cantidad)
            fila[3].text = _pesos(linea.precio_unitario)
            fila[4].text = _pesos(linea.subtotal_cop)
    else:
        fila = tabla.add_row().cells
        fila[0].text = pedido.producto.titulo
        fila[1].text = _ficha(pedido.producto, None)
        fila[2].text = str(pedido.cantidad)
        fila[3].text = ""
        fila[4].text = _pesos(pedido.subtotal_cop)

    documento.add_paragraph("")
    documento.add_paragraph(f"Mercancía y envío cobrado en la página: {_pesos(pedido.subtotal_cop)}")
    if pedido.factura_iva:
        documento.add_paragraph(f"Factura con IVA {pedido.iva_pct}%: {_pesos(pedido.iva_cop)}")
    else:
        documento.add_paragraph("Factura sin IVA")
    documento.add_paragraph(f"ERA shop {pedido.comision_pct}%: {_pesos(pedido.comision_cop)}")
    documento.add_paragraph(f"Wompi: {_pesos(pedido.tarifa_pasarela_cop)}")
    total = documento.add_paragraph(f"Total que paga el establecimiento: {_pesos(pedido.monto_cop)}")
    for run in total.runs:
        run.bold = True
    documento.add_paragraph(f"Queda para el proveedor: {_pesos(pedido.neto_vendedor)}")
    if pedido.modo_envio == "contraentrega":
        documento.add_paragraph("El envío se paga contraentrega. No está dentro del total de la página.")
    elif pedido.modo_envio == "incluido":
        documento.add_paragraph("El envío va incluido en el precio.")
    elif pedido.envio_cop:
        documento.add_paragraph(f"Envío cobrado en el pedido: {_pesos(pedido.envio_cop)}")

    for seccion in documento.sections:
        seccion.top_margin = Cm(1.5)
        seccion.bottom_margin = Cm(1.5)
        seccion.left_margin = Cm(1.5)
        seccion.right_margin = Cm(1.5)

    salida = BytesIO()
    documento.save(salida)
    return salida.getvalue()


def _ficha(producto, linea):
    partes = []
    if producto.sku:
        partes.append(f"Ref. {producto.sku}")
    if producto.marca:
        partes.append(producto.marca)
    if producto.color:
        partes.append(producto.color)
    if producto.talla:
        partes.append(f"Talla {producto.talla}")
    if producto.material:
        partes.append(producto.material)
    if producto.unidad_empaque:
        partes.append(producto.unidad_empaque)
    modo = linea.modo_envio if linea is not None else producto.modo_envio
    if modo == "contraentrega":
        partes.append("Envío contraentrega")
    elif modo == "aparte" and linea is not None and linea.envio_cop:
        partes.append(f"Envío {_pesos(linea.envio_cop)}")
    elif modo == "incluido":
        partes.append("Envío incluido")
    return " · ".join(partes)
