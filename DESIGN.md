---
name: CV Optimizer AI
description: Generador de CVs ATS-optimizados con IA, cruzando historial real del candidato con cada vacante.
colors:
  electric-blue: "#58a6ff"
  dark-canvas: "#0d1117"
  dark-surface: "#161b22"
  silver-body: "#c9d1d9"
typography:
  body:
    fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  sm: "4px"
  md: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.electric-blue}"
    textColor: "{colors.dark-canvas}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.electric-blue}"
    textColor: "{colors.dark-canvas}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
---
# Design System: CV Optimizer AI

## 1. Overview

**Creative North Star: "El Taller Nocturno"**

La interfaz evoca la atmósfera de un taller técnico bien iluminado de noche: confianza profesional con una calidez acogedora. Como un editor de código moderno que no intimida, sino que invita a trabajar. La oscuridad del fondo (dark-canvas) proporciona el foco; el azul eléctrico del acento (electric-blue) guía la mirada hacia las acciones importantes sin gritar. El sistema es deliberadamente austero: pocos colores, mucho espacio, cero decoración. Lo que importa es el contenido del usuario —sus experiencias, sus habilidades, su CV— y la interfaz existe solo para servir ese propósito.

El sistema rechaza explícitamente dos extremos: la saturación corporativa de dashboards recargados y la frialdad del terminal-style que aliena a usuarios no técnicos. Busca el punto medio: una herramienta que se siente profesional y confiable, pero cálida y cercana. La personalidad "cercano, motivador, simple" de PRODUCT.md se traduce en decisiones visuales que reducen la carga cognitiva y transmiten que cada paso está bajo control.

**Key Characteristics:**
- Tema oscuro con un único acento azul quirúrgico.
- Plano por defecto; las sombras solo aparecen como respuesta a la interacción (hover, focus, selección).
- Tipografía Plus Jakarta Sans: amigable y moderna sin perder profesionalismo. Una sola familia para todo.
- Componentes nativos de Streamlit con personalización mínima: no se reinventan affordances estándar.

## 2. Colors

Una paleta oscura de cuatro tonos, heredada del lenguaje visual de GitHub Dark. El acento azul es el único color saturado; su rareza es su poder.

### Primary
- **Electric Blue** (#58a6ff): Encabezados H1/H2, enlaces, botones de acción primaria, indicadores de estado activo. Usado con moderación: ≤10% de cualquier pantalla.

### Neutral
- **Dark Canvas** (#0d1117): Fondo principal de la aplicación. El lienzo sobre el que descansa todo. También usado en inputs de texto.
- **Dark Surface** (#161b22): Sidebar y contenedores secundarios. Ligeramente más claro que el canvas para crear separación tonal sin bordes.
- **Silver Body** (#c9d1d9): Texto de cuerpo, labels, placeholders. Contraste verificado: 9.1:1 sobre Dark Canvas, 8.5:1 sobre Dark Surface. Supera ampliamente WCAG AA.

### Named Rules
**The One Voice Rule.** El acento Electric Blue se usa solo para acciones primarias, selección actual e indicadores de estado. Nunca como decoración de fondo, borde decorativo ni gradiente. Su escasez es el punto.

## 3. Typography

**Body Font:** Plus Jakarta Sans (con fallback a system-ui stack: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif)
**Label/Mono Font:** Misma stack; no se necesita monoespaciada separada.

**Character:** Plus Jakarta Sans es una sans-serif geométrica con calidez. Su diseño "friendly, modern, clean, approachable" encaja con la personalidad "cercano, motivador, simple" de PRODUCT.md. Una sola familia para todo: encabezados, botones, labels, cuerpo. Se importa desde Google Fonts; el sistema operativo hace fallback mientras carga. Sin display fonts ni adornos tipográficos.

**Google Fonts Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
```

### Hierarchy
- **Headline** (600, 1.5rem/24px, 1.3): Títulos de página y secciones principales. Color: Electric Blue.
- **Title** (600, 1.25rem/20px, 1.4): Subtítulos de sección, encabezados de tarjeta. Color: Silver Body.
- **Body** (400, 1rem/16px, 1.6): Texto de cuerpo, descripciones, viñetas. Color: Silver Body. Línea máxima 65-75ch en prosa; datos y tablas pueden ser más densos.
- **Label** (500, 0.875rem/14px, 1.4): Labels de formulario, tabs, chips, metadatos. Color: Silver Body con opacidad 0.8.

### Named Rules
**The Familiar Default Rule.** Plus Jakarta Sans es la primaria; si no carga, la system-ui stack del SO toma el control. La experiencia nunca se degrada por una fuente faltante.

## 4. Elevation

Sistema plano en reposo. La separación entre superficies se logra mediante contraste tonal (Dark Canvas → Dark Surface), no con sombras. Las sombras aparecen exclusivamente como respuesta a estado: hover, focus, o selección activa de un elemento. Son ligeras, difusas y funcionales, nunca decorativas.

### Shadow Vocabulary
- **Hover Lift** (`box-shadow: 0 2px 8px rgba(0,0,0,0.3)`): Botones y elementos interactivos al pasar el cursor. Transición suave de 150ms ease-out.
- **Focus Glow** (`box-shadow: 0 0 0 2px #58a6ff`): Anillos de foco en inputs y controles. Usa el Electric Blue para consistencia con el acento.

### Named Rules
**The Flat-By-Default Rule.** Las superficies son planas en reposo. Las sombras solo aparecen como respuesta a estado (hover, focus, selección). Si un elemento tiene sombra sin interacción, está mal.

## 5. Components

Los componentes son los nativos de Streamlit con personalización mínima de color y forma. No se reinventan affordances estándar.

### Buttons
- **Shape:** Bordes redondeados sutiles (4px radius).
- **Primary:** Fondo Electric Blue (#58a6ff), texto Dark Canvas (#0d1117), padding 8px 16px. Transición de background 150ms ease-out.
- **Hover / Focus:** Mismo fondo, elevación sutil (Hover Lift shadow). Sin cambio de color; la sombra es el feedback.
- **Disabled:** Opacidad 40%, sin sombra, sin cursor pointer.

### Tabs
- **Style:** Navegación horizontal sobre Dark Canvas. Tab activo: borde inferior Electric Blue de 2px, texto Electric Blue. Tab inactivo: sin borde, texto Silver Body con opacidad 0.7.
- **Hover:** Tab inactivo → texto Silver Body con opacidad 1.0. Sin sombra.

### Inputs / Fields
- **Style:** Fondo Dark Canvas (#0d1117), borde 1px solid con opacidad 0.2 de Silver Body, texto Silver Body, radius 4px.
- **Focus:** Borde Electric Blue, Focus Glow. Transición 150ms ease-out.
- **Error:** Borde en rojo tenue (#f85149), sin glow azul. Mensaje de error en el mismo rojo.
- **Disabled:** Opacidad 40%, sin interacción.

### Sidebar
- **Style:** Fondo Dark Surface (#161b22), ancho fijo (Streamlit default), sin borde ni sombra. La separación del contenido principal es puramente tonal.
- **Typography:** Misma jerarquía que el contenido principal.

### Expanders / Acordeones
- **Style:** Sin fondo propio; heredan Dark Canvas. Toggle con ícono nativo de Streamlit en Silver Body.
- **Hover:** Sin sombra; solo cambio de opacidad en el ícono toggle.

### Cards / Containers
- **Style:** Streamlit no tiene cards nativas; los contenedores usan el fondo heredado. Si se introducen cards en el futuro: fondo Dark Surface, radius 8px, sin sombra en reposo.

## 6. Do's and Don'ts

### Do:
- **Do** mantener el tema oscuro consistente en todas las pantallas. Dark Canvas de fondo, Dark Surface para áreas secundarias.
- **Do** usar Electric Blue (#58a6ff) solo para acciones primarias, navegación activa e indicadores de estado. Su escasez es intencional.
- **Do** usar contrastes tonales (Dark Canvas vs Dark Surface) para separar regiones, no bordes ni sombras.
- **Do** verificar contraste de texto: Silver Body sobre Dark Canvas debe mantener ≥7:1 (actualmente 9.1:1).
- **Do** usar Plus Jakarta Sans con fallback a system-ui. La tipografía amigable refuerza la personalidad cercana.
- **Do** proveer feedback visual en cada interacción: hover lift, focus glow, cambio de opacidad.
- **Do** mantener transiciones rápidas: 150-200ms ease-out. El usuario está en flujo de trabajo, no viendo una animación.

### Don't:
- **Don't** introducir colores adicionales sin un rol semántico claro. La paleta tiene 4 colores por diseño.
- **Don't** usar sombras decorativas en elementos estáticos. Solo como respuesta a interacción (The Flat-By-Default Rule).
- **Don't** saturar la interfaz con gradientes, glassmorphism, bordes decorativos ni side-stripe accents. Rechazado por PRODUCT.md como "recargado o corporativo-genérico".
- **Don't** volver la interfaz monocromática extrema o terminal-style. PRODUCT.md lo rechaza explícitamente como "frío o terminal-style".
- **Don't** usar fuentes display, serif ni monoespaciadas para cuerpo o labels. Una sola familia sans-serif del sistema.
- **Don't** reinventar affordances estándar de formularios, modales o navegación. Streamlit proporciona los patrones; personalizar solo color y forma.
- **Don't** usar animaciones orquestadas de entrada. La herramienta carga al instante; el usuario no debe esperar coreografía.

### Pre-delivery Checklist
- [ ] No emojis ni Material icons: interfaz limpia con texto y estados de color nativos de Streamlit
- [ ] `cursor: pointer` en todos los elementos clickeables
- [ ] Estados hover con transiciones suaves (150-300ms)
- [ ] Contraste de texto ≥4.5:1 en todos los modos (actualmente 9.1:1)
- [ ] Estados de focus visibles para navegación por teclado
- [ ] `prefers-reduced-motion` respetado en todas las animaciones
- [ ] Feedback de submit en formularios: loading → success/error
- [ ] Indicadores de progreso en procesos multi-paso
- [ ] Labels visibles en todos los inputs (nunca solo placeholder)
