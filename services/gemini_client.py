import base64
import logging

import requests

from config import (
    GEMINI_BASE_URL,
    GEMINI_MODEL,
    LLM_TIMEOUT_SECONDS,
    PROMPT_VERSION,
    SKILL_CATEGORIES,
)
from utils.retry import RetryableError

logger = logging.getLogger(__name__)


class JobParsingError(Exception):
    pass


_SECTION_TITLES = {
    "es": ("Perfil Profesional", "Experiencia Laboral", "Educación", "Habilidades"),
    "en": ("Professional Summary", "Work Experience", "Education", "Skills"),
}


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = GEMINI_MODEL,
        prompt_version: str = PROMPT_VERSION,
    ):
        self.api_key = api_key
        self.model = model
        self.prompt_version = prompt_version
        self._base_url = f"{GEMINI_BASE_URL}/{model}:generateContent"
        self._headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }

    def _build_payload(self, parts: list[dict]) -> dict:
        return {"contents": [{"parts": parts}]}

    def _call_api(self, payload: dict) -> str:
        try:
            response = requests.post(
                self._base_url, headers=self._headers, json=payload, timeout=LLM_TIMEOUT_SECONDS
            )
        except requests.ConnectionError as e:
            raise RetryableError(f"Error de conexión con Gemini: {e}") from e
        except requests.Timeout as e:
            raise RuntimeError("Gemini tardó demasiado en responder. Intenta de nuevo.") from e
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        elif response.status_code in (429, 503):
            raise RetryableError(f"Status {response.status_code}: {response.text[:200]}")
        else:
            raise RuntimeError(f"API error {response.status_code}: {response.text[:500]}")

    # ── analyze_job_posting ────────────────────────────────────────────

    def analyze_job_posting(
        self,
        text: str = "",
        image_data: bytes | None = None,
        image_mime: str = "",
    ) -> str:
        parts = []

        if image_data:
            img_b64 = base64.b64encode(image_data).decode("utf-8")
            parts.append({"inlineData": {"mimeType": image_mime, "data": img_b64}})
        if text and text.strip():
            combined_text = f"Texto complementario de la vacante proporcionado por el usuario:\n{text.strip()}"
            parts.append({"text": combined_text})

        if self.prompt_version == "v2":
            prompt = (
                "Eres un extractor ATS. Recibes descripciones de empleo de cualquier fuente "
                "(LinkedIn, Indeed, portales corporativos, transcripciones de imágenes). "
                "Extrae los metadatos clave y normalízalos bajo esta estructura exacta:\n\n"
                "ROLE: [Nombre exacto del cargo]\n"
                "COMPANY: [Nombre de la empresa]\n"
                "LOCATION: [Ubicación / Remoto]\n"
                "SENIORITY: [Junior / Semi-Senior / Senior / Lead / Director]\n"
                "CONTRACT TYPE: [Tiempo completo / Medio tiempo / Contratista / Freelance]\n\n"
                "About the Role:\n[Un párrafo conciso con el propósito del puesto]\n\n"
                "Requirements:\n- [Requisito clave 1]\n- [Requisito clave 2]\n\n"
                "Responsibilities:\n- [Responsabilidad 1]\n- [Responsabilidad 2]\n\n"
                "REGLAS OBLIGATORIAS:\n"
                "1. Si un campo no aparece en el texto, usa EXACTAMENTE: \"No especificado\".\n"
                "2. Si hay datos contradictorios (ej. dos ubicaciones), extrae el primero.\n"
                "3. Ignora lenguaje promocional o corporativo. Solo datos del rol.\n"
                "4. Si la entrada NO es una oferta de trabajo, devuelve EXACTAMENTE:\n"
                "   ERROR: La entrada no contiene información válida de una vacante.\n"
                "5. Prohibido: introducciones, notas, bloques de código, o texto fuera de la estructura."
            )
        elif self.prompt_version == "v3":
            prompt = (
                "Analiza la información proporcionada (imagen y/o texto) de esta oferta de empleo, "
                "sea de cualquier profesión o sector.\n"
                "Tu único objetivo es actuar como un digitalizador y extractor ATS. Extrae los datos esenciales "
                "y organízalos exactamente bajo esta estructura Markdown limpia:\n\n"
                "ROLE: [Nombre exacto del cargo, tal como aparece]\n"
                "COMPANY: [Nombre de la empresa, o 'No especificada' si no aparece]\n"
                "LANGUAGE: [Código ISO del idioma en que está escrita la oferta: es, en, pt...]\n"
                "AREA: [Área profesional del cargo en 1 a 3 palabras, ej: Administrativa, "
                "Operaciones y logística, Ventas, Tecnología, Salud, Contabilidad]\n\n"
                "About the Role:\n[Un párrafo conciso que resuma el propósito del puesto]\n\n"
                "Requirements:\n- [Requisito clave 1]\n- [Requisito clave 2]... (Extrae conocimientos, herramientas, "
                "software, certificaciones, años de experiencia, formación e idiomas exigidos)\n\n"
                "Responsibilities:\n- [Responsabilidad 1]\n- [Responsabilidad 2]... (Extrae las funciones principales que ejecutará el contratado)\n\n"
                "REGLAS CRÍTICAS:\n"
                "1. Devuelve ÚNICAMENTE el bloque de texto con la estructura solicitada. No agregues introducciones, "
                "ni notas al final, ni uses bloques de código con marcas triples (```markdown).\n"
                "2. Conserva los términos de la oferta en su idioma original; no los traduzcas.\n"
                "3. Si la entrada NO es una oferta de trabajo, devuelve EXACTAMENTE:\n"
                "ERROR: La entrada no contiene información válida de una vacante."
            )
        else:
            prompt = (
                "Analiza la información proporcionada (imagen y/o texto) de esta oferta de empleo.\n"
                "Tu único objetivo es actuar como un digitalizador y extractor ATS. Extrae los datos esenciales "
                "y organízalos exactamente bajo esta estructura Markdown limpia:\n\n"
                "ROLE: [Nombre exacto del cargo]\n"
                "COMPANY: [Nombre de la empresa, o 'No especificada' si no aparece]\n\n"
                "About the Role:\n[Un párrafo conciso que resuma el propósito del puesto]\n\n"
                "Requirements:\n- [Requisito clave 1]\n- [Requisito clave 2]... (Extrae habilidades técnicas, certificaciones o herramientas demandadas)\n\n"
                "Responsibilities:\n- [Responsabilidad 1]\n- [Responsabilidad 2]... (Extrae las funciones principales que ejecutará el contratado)\n\n"
                "REGLA CRÍTICA: Devuelve ÚNICAMENTE el bloque de texto con la estructura solicitada. No agregues introducciones, "
                "ni notas al final, ni uses bloques de código con marcas triples (```markdown)."
            )

        parts.append({"text": prompt})
        payload = self._build_payload(parts)
        result = self._call_api(payload)

        if self.prompt_version in ("v2", "v3") and result.startswith("ERROR:"):
            raise JobParsingError(result)

        return result

    # ── extract_skills_from_vacancy ─────────────────────────────────────

    def extract_skills_from_vacancy(self, vacancy_analysis: str) -> str:
        prompt = (
            "Extrae TODAS las habilidades concretas mencionadas en esta oferta de trabajo: "
            "herramientas, software, plataformas, conocimientos del área, procesos, metodologías, "
            "certificaciones, idiomas y competencias. Usa el nombre tal como aparece en la oferta. "
            "Devuelve UNA por línea, solo el nombre, sin guiones, viñetas ni formato adicional.\n\n"
            f"{vacancy_analysis}"
        )
        parts = [{"text": prompt}]
        payload = self._build_payload(parts)
        return self._call_api(payload)

    # ── polish_experience ──────────────────────────────────────────────

    def polish_experience(
        self,
        role: str,
        company: str,
        period: str,
        country: str,
        modality: str,
        raw_details: str,
    ) -> str:
        if self.prompt_version == "v2":
            prompt = f"""
Eres un Especialista en Ingeniería de Currículums TI. Conviertes notas crudas
—telegráficas, narrativas o semi-estructuradas— en descripciones técnicas maestras
para una Base de Conocimiento que alimentará un matcher ATS.

DATOS DE ENTRADA:
- Cargo: {role}
- Empresa: {company}
- Periodo: {period}
- País: {country}
- Modalidad: {modality}
- Detalles crudos: {raw_details}

REGLAS OBLIGATORIAS:

1. ENCABEZADO: Genera exactamente: ### {role} - {company} | {period} | {country} | {modality}

2. PROCESAMIENTO SEGÚN TIPO DE INPUT:
   - Telegráfico (palabras sueltas): conecta los conceptos en flujos de trabajo lógicos.
   - Narrativo informal: extrae acciones clave, elimina tono coloquial, convierte en hitos técnicos.
   - Semi-estructurado (viñetas básicas): eleva el nivel técnico y añade contexto metodológico.

3. EXPANDIR, NUNCA RESUMIR: No omitas ninguna herramienta, tecnología o responsabilidad
   mencionada. Si el usuario dice "migración servidores", expándelo a "planificación,
   ejecución y documentación de la migración". Añade contexto técnico siempre.

4. VERBOS FUERTES EN PRIMERA PERSONA: Cada viñeta empieza con un verbo en primera persona
   del pasado. Usa: Implementé, Diseñé, Lideré, Optimicé, Administré, Arquitecté, Automatizé,
   Desplegué, Integré, Reduje. PROHIBIDO: "Responsable de", "Encargado de", "A cargo de",
   "Participé en", "Apoyé en", "Colaboré en", verbos en tercera persona.

5. INFERENCIA TÉCNICA CONTROLADA: Puedes inferir tecnologías satélite estrictamente comunes
   al stack mencionado (ej. DNS/DHCP si se menciona Active Directory; Agile/Scrum si se
   menciona Jira). PROHIBIDO: inventar lenguajes de programación, frameworks, plataformas
   Cloud o bases de datos que el usuario no haya mencionado ni insinuado.

6. MÉTRICAS: Si el usuario proporciona números (usuarios, servidores, porcentajes),
   consérvalos y ubícalos en contexto. Si NO hay números, NO inventes métricas. En su lugar,
   describe el alcance concreto: "soportando 200+ endpoints", "gestionando infraestructura
   multi-sitio", "atendiendo usuarios C-level".

7. LONGITUD: Entre 5 y 8 viñetas.

8. SI EL INPUT ESTÁ VACÍO O ES INCOMPRENSIBLE: Genera entre 3 y 5 viñetas genéricas pero
   profesionales basadas exclusivamente en el nombre del cargo. Desglosa una responsabilidad
   típica del rol en sub-fases (diseño, implementación, pruebas, soporte).

FORMATO DE SALIDA:
Devuelve ÚNICAMENTE el bloque Markdown. Sin introducciones, notas, ni bloques de código.
"""
        elif self.prompt_version == "v3":
            prompt = f"""
Eres un transcriptor experto en documentación de trayectorias profesionales de cualquier área (administrativa, operativa, comercial, técnica, salud, etc.). Tu trabajo es tomar los datos crudos de una nueva experiencia laboral y redactarla en un Markdown limpio, profesional y exhaustivo para que sirva como 'Materia Prima Maestra'.

DATOS DE ENTRADA:
- Cargo: {role}
- Empresa: {company}
- Periodo: {period}
- País: {country}
- Modalidad: {modality}
- Detalles crudos: {raw_details}

REGLAS DE FORMATO MAESTRO:
1. Genera exactamente este encabezado H3: '### {role} - {company} | {period} | {country} | {modality}'
2. Transforma los detalles crudos en una lista de viñetas (entre 3 y 8, según cuánta información real haya). Una tarea por viñeta; no las fusiones ni las omitas.
3. Cada viñeta empieza con un verbo fuerte en primera persona del pasado y usa el vocabulario propio del área del cargo (ej: en administración, facturación, conciliaciones, gestión documental; en operaciones, inventarios, despachos, indicadores).
4. NO INVENTES: no agregues herramientas, software, cifras, porcentajes ni responsabilidades que no estén en los detalles crudos. Puedes ordenar, aclarar y profesionalizar la redacción, pero cada dato debe venir del usuario. Si el usuario da cifras, consérvalas exactas.
5. Devuelve ÚNICAMENTE el bloque Markdown correspondiente a esta experiencia. Sin textos introductorios, sin notas, ni bloques de código.
"""
        else:
            prompt = f"""
Eres un transcriptor experto en documentación de carreras de TI. Tu trabajo es tomar los datos crudos de una nueva experiencia laboral y redactarla en un Markdown limpio, profesional y exhaustivo para que sirva como 'Materia Prima Maestra'.

DATOS DE ENTRADA:
- Cargo: {role}
- Empresa: {company}
- Periodo: {period}
- País: {country}
- Modalidad: {modality}
- Detalles crudos: {raw_details}

REGLAS DE FORMATO MAESTRO:
1. Genera exactamente este encabezado H3: '### {role} - {company} | {period} | {country} | {modality}'
2. Transforma los detalles crudos en una lista de viñetas (entre 5 y 8 viñetas).
3. Cada viñeta debe expandir la información técnica de forma detallada, usando verbos fuertes en primera persona. Al ser la base maestra, debe ser rica en detalles técnicos.
4. Devuelve ÚNICAMENTE el bloque Markdown correspondiente a esta experiencia. Sin textos introductorios, sin notas, ni bloques de código.
"""

        parts = [{"text": prompt}]
        payload = self._build_payload(parts)
        return self._call_api(payload)

    # ── generate_cv ────────────────────────────────────────────────────

    def generate_cv(
        self,
        job_posting: str,
        experiences: str,
        skills: str,
        education: str,
        extra_focus: str = "",
        user_full_name: str = "",
        language: str = "",
        area: str = "",
    ) -> str:
        focus_text = extra_focus if extra_focus else "Ninguno, haz el mejor match posible."
        cv_language_code = language.strip().lower()[:2]
        cv_language = language.strip() or "el mismo idioma en que está escrita la vacante"
        cv_area = area.strip() or "la que se deduzca de la vacante"

        if self.prompt_version == "v2":
            prompt = f"""
Eres un redactor de CVs optimizado para ATS. Genera un CV de UNA PÁGINA en Markdown
cruzando la base maestra del candidato con la vacante objetivo. No inventes nada.

INSUMOS:
1. VACANTE OBJETIVO:
{job_posting}

2. BASE MAESTRA DE EXPERIENCIAS:
{experiences}

3. BASE MAESTRA DE HABILIDADES:
{skills}

4. BASE MAESTRA DE EDUCACIÓN:
{education}

5. ENFOQUE ADICIONAL:
{focus_text}

REGLAS OBLIGATORIAS:

1. CARGOS REALES: Conserva el cargo real de cada experiencia; nunca lo reemplaces
   por el de la vacante. El Perfil Profesional DEBE abrir con el ROLE exacto de la
   vacante, en el MISMO IDIOMA (ej: "Support Engineer con...").

2. KEYWORDS OBLIGATORIAS: Toda tecnología, herramienta o plataforma mencionada
   por nombre en los Requirements de la vacante DEBE aparecer al menos UNA VEZ
   en el CV (Perfil, logros o Technical Skills). Si está en la base maestra del
   candidato, inclúyela. SIN EXCEPCIÓN.

3. LÍMITE DE UNA PÁGINA A4: El CV DEBE caber en una sola página A4 con fuente ~10pt.
   - Máximo 2 experiencias laborales, máximo 3 viñetas por experiencia.
   - Perfil Profesional: 3-4 líneas concisas.
   - Educación: solo la entrada más relevante para esta vacante.
   - Technical Skills: 1-2 líneas, agrupadas.
   Si el contenido no cabe en una página, ELIMINÁ la experiencia o educación
   menos relevante para la vacante. Preferí calidad sobre cantidad.
   NUNCA inventes datos, NUNCA uses fuente más pequeña.

4. CADA VIÑETA: Verbo fuerte en 1ª persona + tecnología concreta mencionada en la
   vacante + resultado o impacto. Ejemplo: "Administré Windows Server (DHCP, DNS)
   garantizando 99.9% de disponibilidad".

5. ANTI-ALUCINACIÓN: PROHIBIDO inventar empresas, títulos, años, habilidades,
   tecnologías o certificaciones que no estén en los insumos. Si la vacante exige
   algo que el candidato no tiene, omítelo en silencio.

ESTRUCTURA EXACTA DE SALIDA:
## Perfil Profesional
[3-4 líneas en 1ª persona, alineadas al ROLE]

## Experiencia Profesional
### [Cargo real] - [Empresa real] | [Periodo] | [País] | [Modalidad]
- [Viñeta con tecnología + impacto]

## Educación
### [Título] - [Institución] | [Periodo]
(Incluye SOLO educación relevante para la vacante)

## Technical Skills
- [Habilidades agrupadas por categoría, solo las relevantes]

Devuelve EXCLUSIVAMENTE el Markdown del CV. Sin introducciones, notas ni bloques de código.
"""
        elif self.prompt_version == "v3":
            titles = _SECTION_TITLES.get(cv_language_code, _SECTION_TITLES["es"])
            titles_note = (
                "" if cv_language_code in _SECTION_TITLES
                else " (tradúcelos al idioma del CV si no es español)"
            )
            prompt = f"""
Eres un redactor profesional de CVs y experto en filtros ATS para cualquier profesión y sector (administrativo, operativo, comercial, técnico, salud, etc.). Tu objetivo es construir un Currículum Vitae en Markdown persuasivo y 100% veraz, cruzando cinco insumos y siguiendo la estructura indicada.

CONTEXTO DE LA VACANTE:
- Área profesional: {cv_area}
- Idioma del CV: {cv_language}

INSUMOS DISPONIBLES:
1. VACANTE OBJETIVO:
{job_posting}

2. MI BASE MAESTRA DE EXPERIENCIAS:
{experiences}

3. MI LISTA MAESTRA DE HABILIDADES:
{skills}

4. MI BASE MAESTRA DE EDUCACIÓN Y CERTIFICADOS:
{education}

5. ENFOQUE ADICIONAL SOLICITADO POR EL USUARIO:
{focus_text}

INSTRUCCIONES DE CONSTRUCCIÓN (REGLAS OBLIGATORIAS):
1. IDIOMA: Redacta TODO el CV en el idioma del CV indicado arriba, incluidos los títulos de sección. Si la base maestra está en otro idioma, tradúcela fielmente sin cambiar su significado. Los nombres de empresas e instituciones no se traducen.

2. VOCABULARIO DEL ÁREA: Usa la terminología, los tipos de logros y los indicadores que se valoran en el área de la vacante, tomando como referencia las palabras de la propia vacante. Nunca le des un enfoque tecnológico a un CV cuya vacante no es de tecnología.

3. PERFIL PROFESIONAL: 3-4 líneas en primera persona. DEBE abrir con el cargo EXACTO del ROLE de la vacante (ej: "Auxiliar Administrativa con 4 años de experiencia en..."), seguido de la experiencia y fortalezas reales más relevantes para la vacante.

4. CARGOS REALES (CRÍTICO): Conserva el nombre real del cargo de cada experiencia tal como aparece en la base maestra (traducido si el CV va en otro idioma); nunca lo reemplaces por el de la vacante. Falsificar un cargo se descubre al verificar referencias.

5. SELECCIÓN: Selecciona entre 2 y 3 experiencias de la base maestra que más valor agreguen a la vacante (si solo hay 1, usa esa). Prioriza las de mayor duración, salvo que una corta sea mucho más relevante. Omite experiencias, habilidades o educación sin valor directo o indirecto para la vacante.

6. PALABRAS CLAVE: Incluye al menos una vez cada requisito o palabra clave de la vacante que esté RESPALDADO por los insumos, de forma natural (en el Perfil, los logros o las Habilidades) y usando el mismo término que usa la vacante. No repitas palabras clave artificialmente. Si la vacante pide algo que el candidato no tiene, omítelo en silencio.

7. VIÑETAS: Entre 8 y 12 viñetas en total sumando todas las experiencias, mínimo 2 por experiencia, según cuánto material real haya. NUNCA rellenes para alcanzar un número. Cada viñeta: verbo de acción en primera persona del pasado + qué se hizo + resultado o alcance. Usa cifras SOLO si están en la base maestra; si no las hay, describe el alcance concreto sin inventar números.

8. NO INVENTES (CRÍTICO): Prohibido agregar empresas, cargos, fechas, títulos, certificaciones, herramientas, software, cifras o responsabilidades que no estén en los insumos.

9. EDUCACIÓN: Máximo 4 entradas, las más relevantes para la vacante. Cada una en UNA SOLA LÍNEA H3: ### [Título] - [Institución] | [Periodo]. Sin viñetas ni descripciones debajo.

10. HABILIDADES: Lista de viñetas agrupadas por categorías pertinentes al área (ej: "- **Herramientas:** Excel avanzado, SAP"), con las más relevantes para la vacante primero. Solo habilidades presentes en los insumos.

11. UNA PÁGINA A4: El CV debe caber en una sola página. Si no cabe, acorta las viñetas o quita las menos relevantes.

12. ORDEN CRONOLÓGICO: Experiencias en orden cronológico inverso (la más reciente primero).

13. ESTRUCTURA: Usa exactamente estos títulos H2, en este orden{titles_note}:
## {titles[0]}
## {titles[1]}
   (cada entrada: ### [Cargo real] - [Empresa real] | [Periodo] | [País] | [Modalidad], seguida de sus viñetas)
## {titles[2]}
## {titles[3]}

REGLA CRÍTICA FINAL: Devuelve EXCLUSIVAMENTE el texto del currículum en formato Markdown, sin ningún texto introductorio, saludo o explicación adicional antes o después del CV generado. No uses bloques de código.
"""
        else:
            prompt = f"""
Eres un redactor profesional de CVs para el sector tecnológico y experto en optimización de filtros ATS. Tu objetivo es construir un Currículum Vitae en Markdown altamente persuasivo cruzando cinco insumos y siguiendo la estructura de secciones y formato específicos.

INSUMOS DISPONIBLES:
1. VACANTE OBJETIVO:
{job_posting}

2. MI BASE MAESTRA DE EXPERIENCIAS:
{experiences}

3. MI LISTA MAESTRA DE HABILIDADES:
{skills}

4. MI BASE MAESTRA DE EDUCACIÓN Y CERTIFICADOS:
{education}

5. ENFOQUE ADICIONAL SOLICITADO POR EL USUARIO:
{focus_text}

INSTRUCCIONES DE CONSTRUCCIÓN (REGLAS OBLIGATORIAS):
1. PERFIL PROFESIONAL: Redacta un Perfil Profesional conciso (3-4 líneas) en primera persona, que posicione al profesional estratégicamente hacia el ROL de la VACANTE OBJETIVO. Utiliza las palabras clave más relevantes de la vacante.

2. SELECCIÓN DE CONTENIDO INTELIGENTE: Selecciona inteligentemente sólo las experiencias y habilidades de las bases maestras que agreguen valor directo o indirecto a la VACANTE OBJETIVO. No inventes tecnologías, empleos o educación que no estén en los insumos.

3. CARGOS REALES: Conserva el cargo real de cada experiencia laboral; nunca lo reemplaces por el de la vacante. Para el match ATS, abre el Perfil Profesional con el cargo EXACTO del ROLE de la vacante.

4. RELEVANCIA ESTRICTA: Omite cualquier experiencia, habilidad o educación que no aporte valor directo o indirecto a la vacante. Es preferible un CV corto y preciso que uno largo con relleno irrelevante.

5. DENSIDAD DE PALABRAS CLAVE: Extrae las tecnologías, metodologías y competencias mencionadas en Requirements y Responsibilities de la vacante. Distribúyelas de forma natural en el Perfil Profesional, los logros y las Technical Skills. Una palabra clave repetida en diferentes contextos suma puntos ATS.

6. LOGROS CONCISOS: Cada experiencia laboral debe tener entre 3 y 5 viñetas. Cada viñeta debe contener: verbo de acción fuerte + contexto técnico concreto + resultado o impacto medible. Prioriza logros que demuestren las tecnologías y competencias demandadas en la vacante.

7. ESTRUCTURA Y ENCABEZADOS:
    - Utiliza títulos H2 para las secciones principales: "Perfil Profesional", "Educación", "Experiencia Laboral" y "Technical Skills".
    - Para cada entrada en la sección "Experiencia Laboral", utiliza un H3 que contenga el cargo real y la empresa real, seguido del Periodo, País y Modalidad. Ejemplo: ### Senior Software Engineer - Tech Solutions Inc. | Enero 2024 - Presente | Colombia | Remoto
    - Para cada entrada en la sección "Educación", utiliza un H3 con el formato: ### [Nombre de la Certificación o Título] - [Institución] | [Año o Periodo]
    - La sección "Technical Skills" debe ser una lista de viñetas agrupadas por categorías cuando sea posible, con las habilidades más relevantes para la vacante primero.

ORDEN DE SECCIONES (CRÍTICO):
1. Perfil Profesional
2. Educación
3. Experiencia Laboral
4. Technical Skills

REGLA CRÍTICA FINAL: Devuelve EXCLUSIVAMENTE el texto del currículum en formato Markdown, sin ningún texto introductorio, saludo o explicación adicional antes o después del CV generado. No uses bloques de código.
"""

        parts = [{"text": prompt}]
        payload = self._build_payload(parts)
        return self._call_api(payload)

    # ── parse_cv_document ──────────────────────────────────────────────

    def parse_cv_document(self, cv_markdown: str) -> str:
        prompt = f"""Eres un extractor de CVs. Parseá este CV y devolvé EXCLUSIVAMENTE
el siguiente formato Markdown, sin introducciones ni notas:

EXPERIENCIAS:
### [Cargo] - [Empresa] | [Periodo] | [País] | [Modalidad]
- [Logro o responsabilidad 1]
- [Logro o responsabilidad 2]

SKILLS:
- **[Nombre]** -> [Categoría]

EDUCACION:
### [Título o Certificación] - [Institución] | [Periodo]
- [Descripción opcional]

REGLAS:
1. Cada experiencia DEBE tener al menos una viñeta de logro.
2. Las skills DEBEN clasificarse en: {", ".join(SKILL_CATEGORIES)}.
3. Si un campo no está en el CV, usá "No especificado".
4. PROHIBIDO inventar datos. Solo extraé lo que esté en el CV.

CV A PROCESAR:
{cv_markdown}"""
        parts = [{"text": prompt}]
        payload = self._build_payload(parts)
        return self._call_api(payload)
