"""Publicaciones de LinkedIn donde etiquetan a la persona: vacantes en posts normales, con texto o con un afiche.

Con la sesión del navegador del bot lee el filtro «Menciones» de las notificaciones y cada publicación: su texto, los
enlaces que trae y sus imágenes. Solo lectura: no comenta, no reacciona y nunca abre los enlaces de la publicación
(LinkedIn los envuelve en /safety/go/?url=…, de donde se toma el destino sin visitarlo). Interfaz de 2026-11: las clases
son aleatorias, así que se usan `data-testid`, enlaces y el orden del documento (el texto, el enlace y las imágenes de la
publicación van antes del cuadro de comentarios y de las reacciones; los comentarios, después)."""

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse

MENTIONS_URL = "https://www.linkedin.com/notifications/?filter=mentions_all"
POST_URL = "https://www.linkedin.com/feed/update/urn:li:activity:{}/"
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 1_200_000  # lo que acepta la app por imagen
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")

_ACTIVITY = re.compile(r"urn:li:activity:(\d+)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)
_JOB = re.compile(r"(contrat|vacante|buscamos|estamos buscando|empleo|oportunidad laboral|oferta laboral|hiring|"
                  r"postula|postular|aplica|hoja de vida|\bh\.?v\b|\bcv\b|curr[ií]cul|requisitos|cargo|se busca|"
                  r"[uú]nete|join (our|the) team|we.?re looking|job|position|salario)", re.I)

# Notificaciones de mención: el enlace lleva la publicación en `highlightedUpdateUrn` o, si la mención fue en un
# comentario, en `dashCommentUrn` (comentario, publicación).
_MENTIONS_JS = """() => [...document.querySelectorAll('main a[href*="highlightedUpdateUrn"]')].map(a => {
  let card = a, text = '';
  for (let i = 0; i < 6 && card.parentElement; i++) {
    card = card.parentElement;
    if (/mencion|mention|etiquet|tagged/i.test(card.innerText)) { text = card.innerText; break; }
  }
  return {href: a.href, text: text.slice(0, 600)};
})"""

# La publicación: lo que está antes del cuadro de comentarios o de las reacciones (lo que sigue son comentarios).
_POST_JS = """(expand) => {
  const main = document.querySelector('main');
  if (!main) return null;
  const marks = [main.querySelector('[data-testid="ui-core-tiptap-text-editor-wrapper"]'),
                 main.querySelector('[data-testid^="ReactionFacepileCollection"]')].filter(Boolean);
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  const end = marks.sort((a, b) => before(a, b) ? -1 : 1)[0] || null;
  const inPost = el => !end || before(el, end);
  const box = [...main.querySelectorAll('[data-testid="expandable-text-box"]')].find(inPost) || null;
  if (expand) {
    const more = box && [...box.parentElement.querySelectorAll('button')]
      .find(b => /^\\s*…?\\s*(ver m[aá]s|m[aá]s|see more|more)\\s*$/i.test(b.innerText));
    if (more) more.click();
    return !!more;
  }
  const people = [...main.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')]
    .filter(a => inPost(a) && (!box || before(a, box)) && a.innerText.trim());
  const author = people.length ? people[people.length - 1].innerText.split(/\\n|•/)[0].trim() : '';
  const links = [...main.querySelectorAll('a[href]')].filter(inPost)
    .map(a => ({href: a.href, text: a.innerText.replace(/\\s+/g, ' ').trim().slice(0, 200)}));
  const images = [...main.querySelectorAll('img')].filter(inPost)
    .filter(i => /media\\.licdn\\.com\\/dms\\/image\\//.test(i.currentSrc || i.src))
    .filter(i => /feedshare/.test(i.currentSrc || i.src) || (i.naturalWidth >= 300
      && !/profile-|company-logo|videocover|articleshare|background/.test(i.currentSrc || i.src)))
    .map(i => i.currentSrc || i.src);
  return {text: box ? box.innerText : '', author, links, images: [...new Set(images)], marked: !!end};
}"""


class SessionError(RuntimeError):
    """LinkedIn pidió iniciar sesión o una verificación: el bot no sigue (nunca resuelve captchas)."""


@dataclass
class Mention:
    activity: str  # id de la publicación
    who: str  # el aviso: «Daniela Maestre te ha mencionado en un comentario»

    @property
    def url(self) -> str:
        return POST_URL.format(self.activity)


@dataclass
class Post:
    activity: str
    author: str = ""
    text: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)  # (destino, texto del enlace), sin repetir
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (contenido, tipo)

    @property
    def url(self) -> str:
        return POST_URL.format(self.activity)

    @property
    def job_links(self) -> list[str]:
        """Ofertas de portales que el bot ya sabe postular (van a la bandeja de la app)."""
        return [url for url, _ in self.links if portal_offer(url)]

    @property
    def other_links(self) -> list[str]:
        return [url for url, _ in self.links if not portal_offer(url)]

    def looks_like_job(self) -> bool:
        """Sin imágenes ni ofertas enlazadas, una publicación sin palabras de empleo no se manda a la IA."""
        return bool(self.images or self.job_links or _JOB.search(self.text))

    def vacancy_text(self) -> str:
        """El texto que analiza la app: quién publica, la publicación y los enlaces que trae (su título ayuda)."""
        parts = [f"Publicación de LinkedIn de {self.author}:" if self.author else "Publicación de LinkedIn:", self.text.strip()]
        if self.links:
            parts.append("Enlaces de la publicación:\n" + "\n".join(f"- {text} — {url}" if text else f"- {url}"
                                                                     for url, text in self.links))
        return "\n\n".join(p for p in parts if p)


def _on(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def emails_in(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(0).rstrip(".") for m in _EMAIL.finditer(text)))


def post_activity(href: str) -> str:
    """El id de la publicación de un aviso de mención («» si el enlace no es de una)."""
    query = parse_qs(urlparse(href).query)
    for key in ("dashCommentUrn", "commentUrn", "highlightedUpdateUrn"):
        for value in query.get(key, []):
            if match := _ACTIVITY.search(unquote(value)):
                return match.group(1)
    match = re.search(r"/feed/update/urn:li:activity:(\d+)", href)
    return match.group(1) if match else ""


def link_target(href: str) -> str:
    """El destino de un enlace de la publicación sin visitarlo: LinkedIn envuelve los externos en /safety/go/?url=…
    Solo http(s); los enlaces internos de LinkedIn que no son ofertas (perfiles, hashtags) se ignoran."""
    parsed = urlparse(href)
    host = (parsed.hostname or "").lower()
    if _on(host, "linkedin.com") and parsed.path.startswith("/safety/go"):
        href = parse_qs(parsed.query).get("url", [""])[0]
        parsed = urlparse(href)
        host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return ""
    if _on(host, "linkedin.com"):
        job = re.search(r"/jobs/view/(?:[^/?#]*?-)?(\d+)", parsed.path) or re.search(r"currentJobId=(\d+)", parsed.query)
        return f"https://www.linkedin.com/jobs/view/{job.group(1)}/" if job else ""
    return href


def portal_offer(url: str) -> str:
    """El portal de una oferta que el bot postula desde la bandeja de la app («» si no es una)."""
    parsed = urlparse(url)
    host, path = (parsed.hostname or "").lower(), parsed.path
    if _on(host, "linkedin.com") and re.search(r"/jobs/view/\d+", path):
        return "linkedin"
    if _on(host, "computrabajo.com") and re.search(r"/ofertas-de-trabajo/.*-[0-9A-Fa-f]{16,}/?$", path):
        return "computrabajo"
    if _on(host, "elempleo.com") and re.search(r"/ofertas-trabajo/.+-\d+/?$", path):
        return "elempleo"
    if _on(host, "magneto365.com") and re.search(r"/(empleos|trabajos)/.+-\d+/?$", path):
        return "magneto"
    return ""


def challenged(page) -> bool:
    from runner.linkedin import CHALLENGE_URL

    return any(part in page.url for part in CHALLENGE_URL)


def mentions(page, *, wait_ms: int = 15_000) -> list[Mention]:
    """Los avisos de «te mencionó» más recientes, una vez por publicación y en el orden de LinkedIn."""
    page.goto(MENTIONS_URL, wait_until="domcontentloaded")
    if challenged(page):
        raise SessionError("LinkedIn pidió iniciar sesión o una verificación")
    try:
        # «attached»: en la interfaz nueva el enlace del aviso no tiene caja visible propia (Playwright lo daría por oculto)
        page.wait_for_selector('main a[href*="highlightedUpdateUrn"]', state="attached", timeout=wait_ms)
    except Exception:  # noqa: BLE001 — sin menciones recientes, o LinkedIn llevó a otra página después de cargar
        if challenged(page):
            raise SessionError("LinkedIn pidió iniciar sesión o una verificación") from None
        return []
    out: dict[str, Mention] = {}
    for item in page.evaluate(_MENTIONS_JS):
        if (activity := post_activity(item["href"])) and activity not in out:
            who = next((line.strip() for line in item["text"].splitlines() if re.search(r"mencion|mention|etiquet|tagged",
                                                                                        line, re.I)), "")
            out[activity] = Mention(activity, who[:200])
    return list(out.values())


def read_post(page, activity: str, *, wait_ms: int = 15_000) -> Post:
    """Texto, autor, enlaces (sin abrirlos) e imágenes (hasta tres) de una publicación. Las imágenes se toman de lo que
    la página ya cargó (ninguna petición aparte)."""
    loaded: dict[str, object] = {}

    def keep(response) -> None:
        if _on((urlparse(response.url).hostname or "").lower(), "media.licdn.com") and "/dms/image/" in response.url:
            loaded[response.url] = response

    page.on("response", keep)
    try:
        page.goto(POST_URL.format(activity), wait_until="domcontentloaded")
        if challenged(page):
            raise SessionError("LinkedIn pidió iniciar sesión o una verificación")
        try:
            page.wait_for_selector('main [data-testid="expandable-text-box"], main [data-testid^="ReactionFacepileCollection"]',
                                   state="attached", timeout=wait_ms)
        except Exception:  # noqa: BLE001
            if challenged(page):
                raise SessionError("LinkedIn pidió iniciar sesión o una verificación") from None
            raise ValueError("la publicación no cargó (quizá la borraron)") from None
        if page.evaluate(_POST_JS, True):  # «…más»: el texto completo
            page.wait_for_timeout(400)
        page.wait_for_timeout(1200)  # el afiche carga después del texto
        raw = page.evaluate(_POST_JS, False) or {}
    finally:
        page.remove_listener("response", keep)
    links: dict[str, str] = {}
    for link in raw.get("links", []):
        if (target := link_target(link["href"])) and target not in links:
            links[target] = link["text"] if link["text"] != target else ""
    post = Post(activity, raw.get("author", ""), (raw.get("text") or "").strip(), list(links.items()))
    for src in raw.get("images", []):
        if len(post.images) < MAX_IMAGES and (image := _image(loaded.get(src))):
            post.images.append(image)
    return post


def _image(response) -> tuple[bytes, str] | None:
    """La imagen tal como la sirvió LinkedIn, si es de un tipo y tamaño que acepta la app."""
    if response is None:
        return None
    try:
        mime = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        body = response.body() if response.ok else b""
    except Exception:  # noqa: BLE001 — una imagen que no se pudo leer no detiene la publicación
        return None
    if mime not in IMAGE_TYPES or not body or len(body) > MAX_IMAGE_BYTES:
        return None
    return body, mime
