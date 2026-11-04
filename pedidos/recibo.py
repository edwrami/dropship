from decimal import Decimal
from io import BytesIO

from docx import Document
from docx.shared import Pt


def _pesos(valor):
    numero = int(Decimal(str(valor or 0)))
    return "$" + f"{numero:,}".replace(",", ".")


def docx_recibo(pedido):
    documento = Document()
    estilo = documento.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(11)

    documento.add_heading(f"Comprobante de pago #{pedido.id}", level=1)
    documento.add_paragraph("ERA shop")
    documento.add_paragraph(f"Fecha {pedido.creado:%d/%m/%Y %H:%M}")
    documento.add_paragraph(f"Referencia {pedido.referencia_pago}")
    documento.add_paragraph(f"Estado del pago: {pedido.get_estado_pago_display()}")
    if pedido.metodo_pago:
        documento.add_paragraph(f"Medio: {pedido.metodo_pago}")

    documento.add_heading("Quién pagó", level=2)
    documento.add_paragraph(pedido.cliente_nombre or "")
    if pedido.cliente_email:
        documento.add_paragraph(pedido.cliente_email)
    ciudad = pedido.cliente_ciudad or ""
    if pedido.cliente_departamento:
        ciudad = f"{ciudad}, {pedido.cliente_departamento}"
    if ciudad:
        documento.add_paragraph(ciudad)

    documento.add_heading("Tienda", level=2)
    if pedido.vendedor_id:
        documento.add_paragraph(f"{pedido.vendedor.nombre_tienda} · {pedido.vendedor.ciudad}")
    else:
        documento.add_paragraph("ERA shop")

    documento.add_heading("Qué se pagó", level=2)
    tabla = documento.add_table(rows=1, cols=4)
    tabla.style = "Table Grid"
    for celda, texto in zip(tabla.rows[0].cells, ("Producto", "Cantidad", "Precio", "Suma")):
        celda.text = texto
    lineas = list(pedido.lineas.all())
    if lineas:
        for linea in lineas:
            fila = tabla.add_row().cells
            fila[0].text = linea.titulo
            fila[1].text = str(linea.cantidad)
            fila[2].text = _pesos(linea.precio_unitario)
            fila[3].text = _pesos(linea.subtotal_cop)
    else:
        fila = tabla.add_row().cells
        fila[0].text = pedido.producto.titulo
        fila[1].text = str(pedido.cantidad)
        fila[2].text = _pesos(pedido.subtotal_cop or pedido.monto_cop)
        fila[3].text = _pesos(pedido.subtotal_cop or pedido.monto_cop)

    if pedido.factura_iva and pedido.iva_cop:
        documento.add_paragraph(f"IVA de la factura: {_pesos(pedido.iva_cop)}")
    if pedido.es_mayor:
        cargos = (pedido.comision_cop or 0) + (pedido.tarifa_pasarela_cop or 0)
        if cargos:
            documento.add_paragraph(
                f"Cargos de la página (porcentaje de ERA shop y tarifa de Wompi): {_pesos(cargos)}"
            )
    documento.add_paragraph(f"Total pagado: {_pesos(pedido.monto_cop)}")
    documento.add_paragraph("Este comprobante certifica el pago registrado en ERA shop.")

    salida = BytesIO()
    documento.save(salida)
    return salida.getvalue()
