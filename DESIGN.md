---
name: CV Optimizer AI
description: La búsqueda de empleo como una tabla de posiciones, en gráfica de transmisión deportiva de día.
colors:
  pitch: "#0d5539"
  pitch-deep: "#093f2a"
  pitch-soft: "#e1eee6"
  on-pitch: "#ffffff"
  on-pitch-2: "#c4dccf"
  chalk: "#e8f35a"
  paper: "#f1f3f5"
  surface: "#ffffff"
  sunk: "#e5e9ec"
  ink: "#14181b"
  ink-2: "#444c52"
  ink-3: "#5f686e"
  rule: "#d4dadf"
  rule-strong: "#a7b0b8"
  up: "#17784f"
  up-bg: "#e1f0e6"
  up-row: "#eef6f1"
  mid: "#8a5706"
  mid-solid: "#c98a12"
  on-mid: "#2b1c02"
  mid-bg: "#fbf0d4"
  mid-row: "#fdf6e6"
  down: "#a5372a"
  down-bg: "#f7e2de"
  down-row: "#fbefed"
  none: "#5f686e"
typography:
  display:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "clamp(2rem, 1.4rem + 2.2vw, 2.85rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "0.005em"
  scoreboard:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "1.9rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  scoreboard-lg:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "clamp(4rem, 3rem + 4vw, 6rem)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.03em"
    fontFeature: "tnum"
  headline:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "1.35rem"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "0.02em"
  title:
    fontFamily: "Barlow, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.06rem"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Barlow, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "tnum"
  label:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "0.82rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.06em"
  table-head:
    fontFamily: "'Barlow Condensed', 'Arial Narrow', sans-serif"
    fontSize: "0.78rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  mark: "2px"
  base: "3px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  panel: "18px"
  xl: "20px"
  2xl: "24px"
  section: "36px"
components:
  button-primary:
    backgroundColor: "{colors.pitch}"
    textColor: "{colors.on-pitch}"
    rounded: "{rounded.base}"
    padding: "8px 16px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.pitch-deep}"
    textColor: "{colors.on-pitch}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "8px 16px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.sunk}"
    textColor: "{colors.ink}"
  button-next-move:
    backgroundColor: "{colors.chalk}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "8px 16px"
    height: "44px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.base}"
    padding: "10px 12px"
    height: "44px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.base}"
    padding: "{spacing.panel}"
  table-head:
    backgroundColor: "{colors.pitch}"
    textColor: "{colors.on-pitch-2}"
    typography: "{typography.table-head}"
    padding: "9px 8px"
  pill-go:
    backgroundColor: "{colors.up-bg}"
    textColor: "{colors.up}"
    rounded: "{rounded.base}"
    padding: "3px 8px"
  pill-wait:
    backgroundColor: "{colors.mid-bg}"
    textColor: "{colors.mid}"
    rounded: "{rounded.base}"
    padding: "3px 8px"
  pill-out:
    backgroundColor: "{colors.down-bg}"
    textColor: "{colors.down}"
    rounded: "{rounded.base}"
    padding: "3px 8px"
  next-move-band:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.base}"
    padding: "14px 18px"
  pos-box-up:
    backgroundColor: "{colors.up}"
    textColor: "{colors.on-pitch}"
    rounded: "{rounded.base}"
    size: "32px"
  pos-box-mid:
    backgroundColor: "{colors.mid-solid}"
    textColor: "{colors.on-mid}"
    rounded: "{rounded.base}"
    size: "32px"
  pos-box-down:
    backgroundColor: "{colors.down}"
    textColor: "{colors.on-pitch}"
    rounded: "{rounded.base}"
    size: "32px"
---

# Design System: CV Optimizer AI

## Overview

**Creative North Star: "La Tabla de Posiciones"**

La búsqueda de empleo se lee como la tabla de una liga de fútbol, dibujada con la gráfica de una transmisión deportiva de día. Cada vacante ocupa un puesto según cuánto calza con lo que la persona de verdad hizo; cada postulación tiene un resultado. El papel es blanco frío, la tinta casi negra y el único color comprometido es el verde cancha: la franja superior, las cabeceras de tabla y el botón principal. Todo lo demás es tinta, reglas finas y las tres zonas de la tabla.

La densidad es la de una tabla de resultados: columnas alineadas, números tabulares grandes en Barlow Condensed, rótulos en mayúsculas, cuerpo legible en Barlow. La profundidad no existe; la jerarquía sale del contraste de escala (un numeral de 6rem junto a un cuerpo de 16px), de las reglas (1px finas, 2px de tinta como línea de corte) y de las zonas teñidas. Una sola banda casi negra, «Tu próxima jugada», propone una sola decisión y es el único lugar donde aparece la cal amarilla como acción.

El sistema rechaza el dashboard de tarjetas apiladas y el tema oscuro estilo GitHub que tuvo antes. Ningún estado depende solo del color: siempre lleva texto o una marca dibujada.

**Key Characteristics:**
- Blanco frío, tinta casi negra y verde cancha como único color comprometido.
- Tres zonas (clasificación ≥75, repechaje 50–74, descenso <50 o cerrada) siempre nombradas con texto.
- Barlow Condensed en mayúsculas para rótulos y numerales tabulares; Barlow para el cuerpo.
- Plano: reglas finas, sin sombras de elevación, esquinas de 3px.
- Cal amarilla reservada a tres usos: la acción de «Tu próxima jugada», la línea activa de la navegación en escritorio y el foco sobre fondos oscuros.
- Primero el celular: navegación inferior, tablas en filas de dos líneas, objetivos táctiles de 44px.

## Colors

Una paleta de transmisión de día: papel frío, tinta, un verde cancha profundo y tres tintas de zona apagadas, con una marca de cal amarilla que casi nunca aparece.

### Primary
- **Verde Cancha** (pitch): la franja superior sticky, el fondo de las cabeceras de tabla, el botón principal, enlaces, la barra activa de la navegación inferior, el cursor de texto, la selección y el anillo de foco sobre fondo claro.
- **Verde Cancha Hondo** (pitch-deep): hover del botón principal y de los botones dentro de la franja.
- **Verde Cancha Suave** (pitch-soft): avisos informativos y la pastilla «en preparación».
- **Blanco sobre Cancha** (on-pitch) y **Verde Ceniza** (on-pitch-2): texto e íconos sobre la franja y las cabeceras; el ceniza para lo inactivo (navegación no activa, rótulos de cabecera, cupo de IA).

### Secondary
- **Cal** (chalk): la marca de cal de la cancha. Solo en el botón de acción de «Tu próxima jugada», la línea activa de la navegación en escritorio (4px bajo el enlace) y el anillo de foco dentro de la franja y de la banda casi negra.

### Tertiary: zonas y estados
- **Verde Clasificación** (up, con up-bg y up-row): zona ≥75, «cumples», etapas que avanzan.
- **Ámbar Repechaje** (mid como texto, mid-solid como bloque, mid-bg y mid-row): zona 50–74, «a medias», esperas, recordatorios y fechas viejas. El bloque sólido lleva texto café casi negro (on-mid), nunca blanco.
- **Rojo Descenso Apagado** (down, con down-bg y down-row): zona <50 o vacante cerrada, «te falta», rechazos, acciones destructivas.
- **Gris Sin Calcular** (none): puesto sin compatibilidad calculada y resultados neutros.

### Neutral
- **Papel Frío** (paper): fondo de la app y de las cajas para copiar.
- **Superficie** (surface): paneles, tablas, campos, botones secundarios y la navegación inferior.
- **Hundido** (sunk): hover de botones, pastillas y avisos neutros, fondo de barras.
- **Tinta** (ink): texto principal, la banda «Tu próxima jugada», la pestaña seleccionada y las líneas de corte de 2px.
- **Tinta 2** (ink-2) y **Tinta 3** (ink-3): metadatos y rótulos de campo; texto terciario, marcadores de posición y rangos de zona.
- **Regla** (rule) y **Regla Fuerte** (rule-strong): divisiones finas de 1px entre filas y paneles; borde de campos y botones secundarios.

### Named Rules
**La Regla de la Cal.** El amarillo cal aparece en tres sitios y en ninguno más: la acción única de «Tu próxima jugada», la línea activa de la navegación en escritorio y el foco sobre fondos oscuros. Nunca como fondo de superficie, nunca sobre papel claro.

**La Regla de la Zona Nombrada.** Una tinta de zona nunca va sola: la acompaña el nombre de la zona, el rango, una marca dibujada o la palabra del estado. El color confirma; el texto informa.

**La Regla del Verde Único.** El verde cancha es el único color de marca. Las tintas de zona son información, no decoración, y no se usan para adornar secciones.

## Typography

**Display Font:** Barlow Condensed (con Arial Narrow, sans-serif), autoalojada en 500, 600 y 700.
**Body Font:** Barlow (con system-ui), autoalojada en 400, 500 y 600.

**Character:** La condensada en mayúsculas es la rotulación del marcador y de la gráfica en pantalla; la Barlow regular es el texto que se lee con calma. Todo el cuerpo usa números tabulares para que las columnas cuadren.

### Hierarchy
- **Display** (700, clamp 2rem–2.85rem, 1.05, mayúsculas): título de página (h1). En la entrada sube hasta 3.4rem.
- **Marcador** (700, 1.9rem, 1, tabular): numerales de la franja de estadísticas, de la compatibilidad en la tabla y de las métricas. La versión grande (clamp 4rem–6rem, -0.03em) es la compatibilidad en la ficha de una postulación.
- **Headline** (700, 1.35rem, mayúsculas, 0.02em): h2; 1.2rem en encabezados de sección y 1.05rem con 0.04em en títulos de panel y resúmenes plegables.
- **Title** (Barlow 600, 1.06rem, 1.3): h3, el cargo de cada vacante y cada empleo en la trayectoria. Va en caja normal.
- **Body** (Barlow 400, 16px, 1.55): texto corrido; los párrafos de encabezado de página se limitan a 62ch.
- **Label** (600, 0.82rem, 0.06em, mayúsculas): rótulos de campo, navegación, cupo de IA, contadores de sección.
- **Cabecera de tabla** (700, 0.78rem, 0.08em, mayúsculas): cabeceras sobre verde cancha, filas de zona, pastillas de estado.

### Named Rules
**La Regla del Marcador.** Todo número que se compara (compatibilidad, conteos, posiciones) va en Barlow Condensed 700 tabular y lo más grande de su contexto; su prueba se lee al lado (zona, rótulo o barra).

**La Regla de las Dos Voces.** Mayúsculas condensadas para nombrar (rótulos, cabeceras, botones de pestaña); Barlow en caja normal para todo lo que se lee como frase, incluidos los cargos y los botones.

## Layout

Una columna central de hasta 1240px con márgenes de 16px en celular y 28px desde 900px. La franja verde (56px) es sticky arriba; en celular la navegación es una barra inferior fija de 64px con cuatro destinos e íconos de trazo, y desde 900px los enlaces suben a la franja.

Desde 1080px la Bandeja usa un riel: la tabla manda a la izquierda y un riel de 330px trae vacantes a la derecha. La ficha de postulación se parte en 1.35:1 desde 1000px. La trayectoria del perfil pone las fechas en una columna de 150px desde 720px.

Los formularios pasan a dos columnas solo cuando su contenedor (panel o fila de trayectoria) mide 520px o más, con container queries; en el riel quedan a una.

En celular (<760px) la tabla de posiciones pierde la cabecera visible y cada vacante se vuelve una fila de cuadrícula: puesto a la izquierda, cargo y compatibilidad arriba, lo que le falta y las acciones debajo. Las franjas de estadísticas (<600px) se vuelven una fila flexible de celdas con su rótulo encima, más una celda final a lo ancho para el dato largo. La lista de resultados apila la fecha arriba.

El ritmo vertical usa 4, 8, 12, 16, 20, 24 y 36px: 12px dentro de pilas, 18px dentro de paneles, 20px entre piezas del riel y 36px entre secciones.

## Elevation & Depth

Sin sombras. La profundidad no se simula: la jerarquía sale de la franja verde, de la banda casi negra, de las superficies blancas sobre papel frío y de las reglas. El único `box-shadow` del sistema es el anillo de foco (2px superficie + 2px verde cancha; 2px tinta + 2px cal en fondos oscuros) y el halo de 3px verde al 18% de los campos enfocados: son señales de estado, no elevación.

### Named Rules
**La Regla de la Cancha Plana.** Ninguna superficie flota. Si algo necesita separarse, recibe una regla de 1px, una línea de corte de 2px en tinta o un cambio de fondo.

**La Regla de la Línea de Corte.** La regla de 2px en tinta marca fronteras con significado: bajo cada encabezado de sección, bajo la cabecera de la ficha de postulación y en cada cambio de zona de la tabla.

## Shapes

Esquinas de 3px en todo lo que es caja: botones, campos, paneles, tablas, pastillas, marcas, la banda y el monograma «CV». Los cuadros pequeños de dato (forma reciente, leyenda de zonas) usan 2px y las barras 1px. El spinner es el único círculo. Las cabeceras de tabla redondean solo sus esquinas superiores. Los bordes son de 1px; la caja vacía usa borde punteado. Las flechas de los plegables y la conexión de evidencia en los requisitos se dibujan con bordes CSS, no con caracteres.

## Components

### Buttons
Directos y planos, con el peso de un botón de mando, no de una tarjeta.
- **Shape:** esquinas de 3px, mínimo 44px de alto (36px en la variante pequeña, que sube a 44px con puntero grueso).
- **Primary:** verde cancha con texto blanco, Barlow 600 1rem, 8px 16px; ícono de 16px a la derecha cuando la acción avanza.
- **Hover / Focus:** el primario pasa a verde hondo; el secundario oscurece su borde a tinta y su fondo a hundido. Transiciones de 140ms. Foco: anillo doble de 2px superficie y 2px verde cancha.
- **Secondary:** superficie blanca con borde regla fuerte. **Ghost:** sin borde, tinta 2. **Link:** subrayado verde que engrosa a 2px. **Danger:** texto y borde rojo descenso, fondo rojo suave al pasar. Deshabilitado al 45% de opacidad.
- **Acción de la próxima jugada:** dentro de la banda casi negra el primario cambia a cal con texto en tinta.

### Chips
- **Style:** superficie con regla de 1px, Barlow 500 0.92rem, botón de quitar de 26px con una cruz dibujada que se tiñe de rojo al pasar.
- **Pastillas de estado:** condensada 700 0.78rem en mayúsculas sobre el fondo suave de su zona (avanzó, esperando, fuera, en preparación).

### Cards / Containers
- **Corner Style:** 3px.
- **Background:** superficie blanca sobre papel frío.
- **Shadow Strategy:** ninguna (ver Elevation & Depth).
- **Border:** regla de 1px.
- **Internal Padding:** 18px. Los paneles nunca se anidan; los plegables usan el mismo título condensado con una flecha de borde que gira.

### Inputs / Fields
- **Style:** superficie blanca, borde regla fuerte, 3px, 10px 12px, mínimo 44px, Barlow 1rem en caja normal. El rótulo va encima en condensada mayúscula 0.82rem.
- **Focus:** borde verde cancha y halo de 3px verde al 18%.
- **Archivo:** el selector nativo se oculta tras un botón secundario con texto en español.

### Navigation
- **Celular:** barra inferior blanca con regla superior, cuatro columnas con ícono de 22px y rótulo condensado 0.82rem; la activa en verde con una barra de 3px arriba.
- **Escritorio (≥900px):** los enlaces viven en la franja verde, en ceniza; hover y activo en blanco; la activa lleva una línea de cal de 4px en la base.
- **Pestañas:** selector segmentado con borde de tinta; la seleccionada se invierte a tinta con texto blanco.

### Tabla de posiciones
La pieza que define el sistema. Cabecera verde cancha; cada fila lleva un cuadro de puesto de 32px teñido sólido por zona, el cargo con empresa, portal y fechas debajo, lo que le falta con marcas dibujadas y la compatibilidad como numeral. Las filas se tiñen con el fondo de su zona y, en cada frontera, una fila de zona con línea de corte de 2px en tinta nombra la zona y su rango. Al pasar o enfocar una fila, las demás bajan al 55% de opacidad. Una vacante cerrada se tacha y baja a descenso.

### Banda «Tu próxima jugada»
Bloque casi negro de 14px 18px con una frase que contiene la decisión y, si existe, un solo botón cal. La decisión vive en la frase y en el botón; no se le antepone un rótulo decorativo. En Postulaciones la misma banda lista lo que vence hoy, sin botón cal.

### Franja de estadísticas
Una fila de tabla con cabecera verde y numerales de marcador (1.9rem, 1.6rem en la variante compacta) con su rótulo debajo: marcador del día en Bandeja, campaña en Postulaciones, ficha en Perfil. La forma reciente se muestra como cuadros de 26px con letra (A, E, R) y su clave escrita al lado.

### Marcas de estado
Cuadros de 22px con un ícono de trazo de 15px sobre el fondo suave de su zona (cumples, a medias, te falta, atención, repetida), siempre con texto para lectores de pantalla. Todos los íconos comparten trazo de 1.8 (2–2.4 en marcas) con extremos redondeados.

### Avisos
Bloques tintados con el fondo suave de su tipo (info, ok, advertencia, error), sin franja lateral; el de error usa texto rojo oscuro.

## Do's and Don'ts

### Do:
- **Do** nombra la zona con texto o marca cada vez que uses su tinta: «Zona de postulación · 75 o más», «Repechaje · 50 a 74», «Descenso · menos de 50 o cerrada».
- **Do** pon los números comparables en Barlow Condensed 700 tabular y su prueba al lado.
- **Do** separa con reglas de 1px y marca fronteras con la línea de corte de 2px en tinta.
- **Do** dibuja los estados como SVG de trazo con texto oculto para lectores de pantalla.
- **Do** mantén 44px de objetivo táctil y el anillo de foco doble de 2px.
- **Do** convierte tablas en filas de dos líneas y franjas de estadísticas en fila flexible más una línea a lo ancho en celular.
- **Do** pasa los formularios a dos columnas solo con container queries desde 520px de contenedor.

### Don't:
- **Don't** uses la cal fuera de sus tres sitios ni pongas más de una acción cal por pantalla.
- **Don't** añadas sombras de elevación; el único box-shadow permitido es el de foco.
- **Don't** apiles tarjetas como dashboard ni anides paneles.
- **Don't** uses caracteres unicode (✓ ½ ✗ ·) como marca de estado.
- **Don't** pongas texto blanco sobre el ámbar sólido de repechaje; va en tinta.
- **Don't** redondees más de 3px ni uses píldoras redondas.
- **Don't** vuelvas al fondo oscuro estilo GitHub ni a acentos azules.
