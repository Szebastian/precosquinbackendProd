-- Seed data: migrate existing 4 news items from news.json to noticias table
-- Run AFTER create_noticias_table.sql

INSERT INTO noticias (category, title, description, image, image_position, thumb_type, thumb_src, thumb_bg, sort_order, is_active)
VALUES
  (
    'FESTIVAL 2026',
    'Se abren las inscripciones para el certamen Nuevos Valores',
    'El Pre Cosquín Puerto Pirámides abre sus puertas a nuevos talentos del folklore argentino. El certamen Nuevos Valores está dirigido a artistas emergentes que buscan dar a conocer su arte en uno de los escenarios más importantes del folklorismo patagónico.',
    'assets/home-background.webp',
    'center center',
    'img',
    'assets/img/cruzBaila.webp',
    'bg-blue',
    1,
    TRUE
  ),
  (
    'NUEVO RUBRO',
    'Nuevo rubro en música: "Expresión Oral Folklórica"',
    'El 55° Pre Cosquín 2027 (Sede Puerto Pirámides) anuncia la incorporación de un nuevo rubro: Expresión Oral Folklórica.',
    '/v1/news/images/5bbda79830b56726d57a76dd19d3af5a.png',
    'bottom left',
    'img',
    'assets/img/logoballena.webp',
    'bg-blue',
    2,
    TRUE
  ),
  (
    'INSTITUCIONAL',
    '¡Presentamos la identidad oficial del Pre-Cosquín 2027!',
    '¡Comienza el camino hacia la plaza Próspero Molina! Te presentamos el logo oficial de la 55.° edición del Certamen para Nuevos Valores Pre-Cosquín 2027.',
    '/v1/news/images/0f1cce32e5bc437539818ed7cfa8fcd2.jpg',
    'center center',
    'img',
    'assets/img/logoballena.webp',
    'bg-blue',
    3,
    TRUE
  ),
  (
    'PATROCINIO',
    'Conocé a los sponsors que hacen posible el Pre-Cosquín 2027',
    'Agradecemos a Hotel Rayentray, Hidroeléctrica El Chocón y Municipalidad de Puerto Pirámides por acompañarnos en esta nueva edición del certamen.',
    'assets/home-background.webp',
    'center center',
    'img',
    'assets/img/LRayentray.webp',
    'bg-blue',
    4,
    TRUE
  );
