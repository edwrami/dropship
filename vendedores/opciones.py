DEPARTAMENTOS = [
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bogotá D.C.", "Bolívar",
    "Boyacá", "Caldas", "Caquetá", "Casanare", "Cauca", "Cesar", "Chocó",
    "Córdoba", "Cundinamarca", "Guainía", "Guaviare", "Huila", "La Guajira",
    "Magdalena", "Meta", "Nariño", "Norte de Santander", "Putumayo", "Quindío",
    "Risaralda", "San Andrés y Providencia", "Santander", "Sucre", "Tolima",
    "Valle del Cauca", "Vaupés", "Vichada",
]

DEPARTAMENTOS_CHOICES = [("", "Selecciona")] + [(d, d) for d in DEPARTAMENTOS]

TIPOS_PROVEEDOR = ("fabricante", "mayorista", "importador")

TIPOS = [
    ("persona", "Persona"),
    ("virtual", "Tienda virtual"),
    ("empresa", "Tienda física"),
    ("fabricante", "Fabricante"),
    ("importador", "Importador"),
    ("mayorista", "Mayorista"),
    ("detallista", "Detallista"),
    ("distribuidor", "Distribuidor"),
    ("dropshipper", "Dropshipper"),
    ("outlet", "Outlet"),
]

RANGOS = [
    ("0_50", "Hasta $50.000"),
    ("50_150", "$50.001 a $150.000"),
    ("150_500", "$150.001 a $500.000"),
    ("500_1500", "$500.001 a $1.500.000"),
    ("1500_5000", "$1.500.001 a $5.000.000"),
    ("5000_mas", "Más de $5.000.000"),
]

CONDICIONES = [
    ("nuevo", "Nuevo"),
    ("usado", "Usado"),
    ("reacondicionado", "Reacondicionado"),
    ("abierto", "Caja abierta"),
]

ENTREGAS = [
    (1, "Entrega en 1 día"),
    (2, "Hasta 2 días"),
    (3, "Hasta 3 días"),
    (5, "Hasta 5 días"),
    (7, "Hasta 7 días"),
    (15, "Hasta 15 días"),
    (30, "Hasta 30 días"),
    (45, "Hasta 45 días"),
]


def banda_precio(valor):
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0
    if v <= 50000:
        return "0_50"
    if v <= 150000:
        return "50_150"
    if v <= 500000:
        return "150_500"
    if v <= 1500000:
        return "500_1500"
    if v <= 5000000:
        return "1500_5000"
    return "5000_mas"


def etiqueta_rango(codigo):
    for clave, nombre in RANGOS:
        if clave == codigo:
            return nombre
    return codigo or "Sin rango"
