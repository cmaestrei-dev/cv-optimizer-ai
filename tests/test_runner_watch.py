"""Vigilar portales de empresas (SuccessFactors): leer resultados, filtrar por cargo y avisar solo lo nuevo."""

from runner import watch

PAGE = """
<a class="jobTitle-link" href="/bancolombia/job/Etipani-Ingenieroa-Software-Backend-%28Junior%29-COL/1451777800/">Ingeniero/a Software Backend (Junior)</a>
<a class="jobTitle-link" href="/bancolombia/job/Etipani-Ingenieroa-Software-Backend-%28Junior%29-COL/1451777800/">Ingeniero/a Software Backend (Junior)</a>
<a class="jobTitle-link" href="/bancolombia/job/X-ANALISTA-III-DE-DATOS/1400000001/">ANALISTA III DE DATOS</a>
<a class="jobTitle-link" href="/bancolombia/job/Y-Practicante-en-Tecnologia/1400000002/">Practicante en Tecnología</a>
<a class="jobTitle-link" href="/bancolombia/job/Z-Asesor-Comercial/1400000003/">Asesor/a Comercial</a>
<a class="jobTitle-link" href="/bancolombia/job/W-Practicante-Economia/1400000004/">Practicante Universitario/a de Ciencias Económicas</a>
"""
SITE = watch.Site(name="Bancolombia", base="https://empleo.grupobancolombia.com", terms=["software"])


def test_parse_and_match():
    rows = watch.parse(PAGE, SITE.base)
    assert [r[0] for r in rows] == ["1451777800", "1400000001", "1400000002", "1400000003", "1400000004"]
    assert rows[0][2].startswith("https://empleo.grupobancolombia.com/bancolombia/job/")
    fits = [title for _, title, _ in rows if watch.matches(SITE, title)]
    assert fits == ["Ingeniero/a Software Backend (Junior)", "Practicante en Tecnología"]  # sin «III», comerciales ni economía


def test_only_new_fitting_offers_are_reported():
    data, calls = {}, []
    get = lambda url: calls.append(url) or PAGE  # noqa: E731
    first = watch.check([SITE], data, get=get)
    assert [n["cargo"] for n in first] == ["Ingeniero/a Software Backend (Junior)", "Practicante en Tecnología"]
    assert "q=software" in calls[0] and len(data["vigiladas"]) == 5
    assert watch.check([SITE], data, get=get) == []  # ya vistas: no se repite el aviso
    assert "postúlate tú" in watch.notice(first)


def test_sites_come_from_the_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[[vigilar]]\nnombre = "Ecopetrol"\nsitio = "https://jobs.ecopetrol.com.co/"\nbuscar = ["practicante"]\n',
                    encoding="utf-8")
    (site,) = watch.load_sites(path)
    assert site.base == "https://jobs.ecopetrol.com.co" and site.terms == ["practicante"] and "junior" in site.include
