"""Árbol de categorías de mercancía. Cada tupla es (grupo, [subcategorías])."""

ARBOL = [
    ("Tecnología y electrónica", [
        "Celulares y smartphones", "Tablets", "Portátiles", "Computadores de escritorio",
        "Monitores", "Componentes de PC", "Almacenamiento y memorias", "Impresoras y escáneres",
        "Redes, routers y wifi", "Televisores", "Audio y sonido", "Audífonos",
        "Parlantes y bocinas", "Cámaras fotográficas", "Cámaras de seguridad", "Drones",
        "Videojuegos y consolas", "Smartwatch y wearables", "Proyectores",
        "Cables, cargadores y pilas", "Accesorios para computador",
    ]),
    ("Moda mujer", [
        "Blusas", "Camisetas mujer", "Vestidos", "Faldas", "Pantalones mujer",
        "Jeans mujer", "Ropa interior mujer", "Ropa deportiva mujer", "Vestidos de baño mujer",
        "Chaquetas y abrigos mujer", "Conjuntos mujer", "Pijamas mujer", "Ropa de maternidad",
        "Zapatos mujer", "Tenis mujer", "Sandalias mujer", "Tacones", "Bolsos y carteras",
        "Joyería mujer", "Relojes mujer", "Gafas mujer", "Pañuelos y accesorios",
    ]),
    ("Moda hombre", [
        "Camisetas hombre", "Camisas", "Pantalones hombre", "Jeans hombre",
        "Ropa interior hombre", "Ropa deportiva hombre", "Chaquetas hombre",
        "Vestidos de baño hombre", "Sudaderas y buzos", "Ropa formal hombre",
        "Pijamas hombre", "Zapatos hombre", "Tenis hombre", "Botas hombre",
        "Morrales hombre", "Relojes hombre", "Gafas hombre", "Corbatas y cinturones",
    ]),
    ("Moda infantil", [
        "Ropa de bebé", "Ropa de niño", "Ropa de niña", "Zapatos infantiles",
        "Uniformes escolares", "Ropa deportiva infantil", "Pijamas infantiles",
        "Accesorios infantiles", "Disfraces infantiles",
    ]),
    ("Calzado", [
        "Tenis", "Zapatos formales", "Botas", "Sandalias", "Chanclas",
        "Calzado de seguridad", "Calzado deportivo", "Zapatos de niña", "Zapatos de niño",
    ]),
    ("Belleza y cuidado personal", [
        "Maquillaje", "Cuidado de la piel", "Cuidado del cabello", "Fragancias y perfumes",
        "Uñas", "Barbería y afeitado", "Higiene personal", "Cuidado bucal",
        "Electrodomésticos de belleza", "Protección solar", "Cosmética natural",
    ]),
    ("Salud y bienestar", [
        "Vitaminas y suplementos", "Equipos médicos", "Ortopedia", "Primeros auxilios",
        "Masajes y bienestar", "Cuidado visual", "Movilidad y rehabilitación",
    ]),
    ("Hogar y decoración", [
        "Muebles de sala", "Muebles de comedor", "Muebles de alcoba", "Colchones y almohadas",
        "Ropa de cama", "Cocina y menaje", "Ollas y utensilios", "Vajilla",
        "Decoración", "Iluminación", "Organización y almacenamiento", "Cortinas y persianas",
        "Alfombras y tapetes", "Baño", "Jardín y terraza", "Textiles del hogar",
    ]),
    ("Electrodomésticos", [
        "Neveras", "Lavadoras", "Secadoras", "Estufas y hornos", "Aires acondicionados",
        "Ventiladores", "Licuadoras", "Ollas arroceras", "Aspiradoras", "Cafeteras",
        "Microondas", "Freidoras", "Planchas", "Calentadores",
    ]),
    ("Bebés", [
        "Coches y sillas de bebé", "Cunas y corrales", "Alimentación del bebé", "Pañales",
        "Lactancia", "Seguridad del bebé", "Higiene del bebé", "Juguetes de bebé",
        "Andadores", "Monitores para bebé",
    ]),
    ("Juguetes y juegos", [
        "Juguetes", "Juegos de mesa", "Muñecos", "Vehículos de juguete",
        "Juguetes educativos", "Peluches", "Construcción y bloques", "Juguetes al aire libre",
        "Rompecabezas",
    ]),
    ("Deportes y fitness", [
        "Gimnasio y fitness", "Ciclismo", "Fútbol", "Baloncesto", "Natación",
        "Camping y outdoor", "Pesca", "Patinaje", "Artes marciales",
        "Running", "Yoga", "Suplementos deportivos", "Ropa deportiva",
    ]),
    ("Vehículos, motos y repuestos", [
        "Repuestos de carro", "Repuestos de moto", "Llantas", "Accesorios de carro",
        "Accesorios de moto", "Lubricantes y fluidos", "Audio para vehículo",
        "Herramientas automotrices", "Cascos", "Baterías para vehículo",
        "Iluminación automotriz", "Cuidado del vehículo",
    ]),
    ("Mascotas", [
        "Alimento para perros", "Alimento para gatos", "Accesorios para mascotas",
        "Higiene de mascotas", "Salud veterinaria", "Acuarios", "Aves",
        "Camas y casas", "Juguetes para mascotas",
    ]),
    ("Alimentos y bebidas", [
        "Despensa", "Snacks", "Bebidas", "Café y té", "Orgánicos",
        "Gourmet", "Abarrotes", "Dulces y chocolates", "Productos sin gluten",
    ]),
    ("Ferretería y construcción", [
        "Herramientas manuales", "Herramientas eléctricas", "Materiales de construcción",
        "Pinturas", "Plomería", "Electricidad", "Seguridad industrial",
        "Cerrajería", "Tornillería y fijaciones", "Pegantes y selladores",
    ]),
    ("Agro e industria", [
        "Insumos agrícolas", "Maquinaria agrícola", "Riego", "Semillas",
        "Veterinaria de finca", "Empaques", "Equipo industrial", "Seguridad agrícola",
    ]),
    ("Oficina y papelería", [
        "Papelería", "Útiles escolares", "Muebles de oficina", "Sillas de oficina",
        "Archivo y organización", "Escritura", "Arte y manualidades", "Impresión y tintas",
    ]),
    ("Libros, música y educación", [
        "Libros", "Textos escolares", "Material didáctico", "Instrumentos musicales",
        "Audio profesional", "Coleccionables", "Películas y música",
    ]),
    ("Joyería, relojes y accesorios", [
        "Joyería", "Plata", "Bisutería", "Relojes", "Gafas",
        "Maletas y viaje", "Billeteras", "Cinturones", "Gorras y sombreros",
    ]),
    ("Fiestas y entretenimiento", [
        "Decoración de fiestas", "Disfraces", "Globos y cotillón", "Descartables",
        "Iluminación para eventos", "Mesas y sillas para eventos",
    ]),
    ("Industrial y empaque", [
        "Empaques y cajas", "Cintas y etiquetas", "Básculas", "Equipo de bodega",
        "Señalización", "Uniformes industriales", "Dotación empresarial",
    ]),
]
