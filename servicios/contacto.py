import re

_TELEFONO = re.compile(r"(?:\+?57[\s.-]*)?(?:3\d{2}|60\d)[\s.-]*\d{3}[\s.-]*\d{4}")
_DIGITO = re.compile(r"(?<!\d)(?:\d[\s.-]*){10,12}(?!\d)")
_MAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_WA = re.compile(r"(?:https?://)?(?:wa\.me|api\.whatsapp\.com|whatsapp)[^\s]*", re.I)
_PALABRAS = re.compile(
    r"\b(?:mi\s+whats?app|escr[ií]beme|ll[aá]mame|este\s+es\s+mi\s+n[uú]mero)\b",
    re.I,
)


def sin_contacto(texto):
    """Quita teléfonos, correos y WhatsApp. El contacto solo sale después del pago."""
    limpio = texto or ""
    limpio = _WA.sub("[contacto después del pago]", limpio)
    limpio = _MAIL.sub("[contacto después del pago]", limpio)
    limpio = _TELEFONO.sub("[contacto después del pago]", limpio)
    limpio = _DIGITO.sub("[contacto después del pago]", limpio)
    limpio = _PALABRAS.sub("hablemos aquí", limpio)
    return limpio.strip()[:2000]
