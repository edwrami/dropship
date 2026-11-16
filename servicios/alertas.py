from django.urls import reverse

from pedidos.avisos import dejar_aviso


def avisar_oferente(oferente, titulo, texto, url=""):
    if oferente is None or not oferente.user_id:
        return
    dejar_aviso([oferente.user], titulo, texto, url)


def avisar_agenda(request, cita):
    url = request.build_absolute_uri(
        reverse("resultado_cita", args=[cita.id]) + f"?clave={cita.clave_contacto}"
    )
    oficio = cita.especialidad.oficio_texto if cita.especialidad_id else cita.oferente.oficio_texto
    avisar_oferente(
        cita.oferente,
        "Alguien agendó un servicio",
        (
            f"Reservaron {oficio} el {cita.inicio.strftime('%d/%m %H:%M')}. "
            f"El cliente ya va a pagar o pagó en la página. "
            f"El teléfono se ve cuando el pago quede aprobado."
        ),
        url,
    )


def avisar_consulta(request, consulta):
    url = request.build_absolute_uri(
        reverse("consulta_servicio", args=[consulta.id]) + f"?clave={consulta.clave}"
    )
    oficio = consulta.especialidad.oficio_texto if consulta.especialidad_id else consulta.oferente.oficio_texto
    avisar_oferente(
        consulta.oferente,
        "Alguien pregunta el precio",
        f"Hay una cotización de {oficio}. Responde la tarifa en la página. No pases WhatsApp ni teléfono.",
        url,
    )


def avisar_mensaje_consulta(request, consulta, autor):
    if autor == "oferente":
        return
    url = request.build_absolute_uri(
        reverse("consulta_servicio", args=[consulta.id]) + f"?clave={consulta.clave}"
    )
    avisar_oferente(
        consulta.oferente,
        "Mensaje nuevo de un cliente",
        "Respondieron en una cotización. Entra a la conversación de ERA shop.",
        url,
    )
