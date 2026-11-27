"""Una postulación por empresa y cargo (2026-11-27: Stefanini recibió 10 «Help Desk Analyst N1» y 6 «On-Site Technical
Support L1», la misma vacante en varias ciudades)."""

from types import SimpleNamespace

from runner import __main__ as cli


def test_same_company_and_title_is_repeated():
    taken = [("stefanini", "help desk analyst n1", 740), ("bancolombia", "ingeniero de software", 9)]
    assert cli._repeated(taken, "Stefanini Latam", "Help Desk Analyst N1") == "ya te postulaste a «Help Desk Analyst N1» en Stefanini Latam"
    assert cli._repeated(taken, "Stefanini", "help desk analyst N1.") != ""            # mayúsculas y puntuación no cuentan
    assert cli._repeated(taken, "Stefanini", "Help Desk Analyst N1", app_id=740) == ""  # la misma postulación
    assert cli._repeated(taken, "Stefanini", "Help Desk Analyst N2") == ""
    assert cli._repeated(taken, "Bancolombia S.A.", "Ingeniero de Software") != ""      # «S.A.» no cuenta
    assert cli._repeated(taken, "Grupo Éxito", "Ingeniero de Software") == ""


def test_generic_company_names_are_never_compared():
    taken = [("", "desarrollador junior", 1)]
    for company in ("", "Confidencial", "Importante empresa del sector", "Reconocida empresa de tecnología"):
        assert cli._job_key(company, "Desarrollador Junior") is None
        assert cli._repeated(taken, company, "Desarrollador Junior") == ""


def test_taken_comes_from_sent_or_prepared_applications():
    apps = [{"id": 1, "company": "Stefanini", "role": "QA Tester", "status": "postulada"},
            {"id": 2, "company": "Stefanini", "role": "Help Desk", "status": "descartada"},
            {"id": 3, "company": "Ceiba", "role": "Tester QA", "status": "cv_generado"},
            {"id": 4, "company": "Confidencial", "role": "Programador", "status": "postulada"}]
    assert cli._taken_jobs(SimpleNamespace(get=lambda path: apps)) == [("stefanini", "qa tester", 1), ("ceiba", "tester qa", 3)]

    def broken(path):
        raise RuntimeError("sin red")

    assert cli._taken_jobs(SimpleNamespace(get=broken)) == []  # el filtro se pierde, la vuelta sigue
