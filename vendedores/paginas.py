from django.conf import settings
from django.http import Http404
from django.shortcuts import render


def _dias():
    return int(getattr(settings, "DIAS_RECLAMO", 5))


def pagina_legal(request, slug):
    dias = _dias()
    paginas = {
        "terminos": {
            "titulo": "Términos de ERA shop",
            "parrafos": [
                "ERA shop es la página donde una persona, una tienda física, una tienda virtual, un fabricante, un mayorista o un importador publica mercancía, y donde un comprador o un establecimiento la pide. El fabricante, el mayorista y el importador venden al detal en su tienda y, además, publican lista al por mayor.",
                "El pago del cliente entra por la página. No se paga por fuera. Cuando la transferencia queda aprobada, el pedido queda registrado y ahí aparece el contacto de quien vende.",
                "En una compra al detal, quien compra paga el precio publicado. De ese valor se descuentan el porcentaje vigente de ERA shop y la tarifa de la pasarela. Quien vende recibe el resto. El porcentaje se muestra al registrarse y puede cambiar para las ventas nuevas.",
                "En una compra al por mayor, el establecimiento paga el precio de la lista, el IVA si pidió factura con IVA, el porcentaje vigente de ERA shop y la tarifa de la pasarela. Quien vende recibe el precio de la lista.",
                "Cada cuenta es de un solo tipo. Quien publica y el establecimiento que compra al por mayor usan correos distintos. Los datos del pedido quedan guardados para quien compra, para quien vende y para ERA shop.",
                "Quien vende marca el empacado, el despacho con transportadora y guía, y la entrega. El reclamo y la devolución se abren dentro del pedido, en el plazo publicado en Devoluciones.",
                "ERA shop puede retirar de la página a quien no liquide una comisión que debía consignar por el camino anterior. En los pagos que entran por la página, el porcentaje ya queda retenido.",
            ],
        },
        "devoluciones": {
            "titulo": "Devoluciones y reclamos",
            "parrafos": [
                f"La devolución se abre en el pedido durante los {dias} días siguientes a la entrega. El reclamo se abre en el mismo pedido mientras no esté cerrado.",
                f"Quien vende tiene {dias} días para responder en la conversación del pedido: aceptar, rechazar o cerrar.",
                "Si ese plazo se cumple y no hay respuesta, el caso pasa a Ventas. ERA shop lo cierra con una de tres decisiones: reponer el producto, devolver el dinero o rechazar el reclamo. Esa decisión queda escrita en el pedido y les llega a las dos partes.",
                "El envío puede ir incluido en el precio, cobrarse aparte dentro del pago, o pagarse contraentrega. Lo que se paga contraentrega no entra en el pago de la página.",
                "El comprobante del pago aprobado se descarga desde el pedido. El pedido al por mayor, además, se descarga en Word para bodega.",
            ],
        },
        "datos": {
            "titulo": "Tratamiento de datos",
            "parrafos": [
                "ERA shop guarda el nombre, la cédula o el NIT, el teléfono, el correo, la dirección y los pedidos. La cédula o el NIT no se publican en el catálogo.",
                "El teléfono, WhatsApp, correo y dirección de quien vende se muestran en el pedido solo cuando la transferencia queda aprobada, y solo a las partes de ese pedido.",
                "Esos datos se usan para crear la cuenta, cobrar, despachar, atender un reclamo y consignar el restante a quien vende. El Nequi de quien vende lo usa ERA shop para ese pago. No se muestra como contacto del catálogo.",
                "Puedes corregir tus datos desde tu cuenta: la ficha de quien vende, la del establecimiento o la del comprador. Para un pedido ya creado, los datos quedan copiados en ese pedido.",
                "ERA shop, como responsable de la página, ve el registro de ventas para operar los pagos y los reclamos.",
            ],
        },
    }
    pagina = paginas.get(slug)
    if pagina is None:
        raise Http404("Página no disponible")
    return render(request, "legal/pagina.html", pagina)
