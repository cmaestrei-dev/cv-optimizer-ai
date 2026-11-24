"""Seguimiento de postulaciones con lo que mostraron los portales reales el 2026-11-24 (sin red ni navegador)."""

from runner import seguimiento as sg

CT_ITEMS = [
    ("A2AAFEC86E8E75D0DE47860191DDD917",
     "Desarrollador de software\nImportante empresa del sector\nCartagena de Indias, Bolívar\nHdV Vista\nHace 5 horas\n"
     "+ 100 candidatos aplicados"),
    ("B1", "Practicante de Proyectos / Calidad / Desarrollo\nHdV Vista\nAyer\n65 candidatos aplicados"),
    ("C1", "Auxiliar de sistemas\nCONTACTAMOS OUTSOURCING S.A.S. 4,5\nManizales, Caldas\nPostulado\nHace 1 minuto\n87 candidatos aplicados"),
]

EE_DETAIL = """Trabajos y empleos en Colombia  Estadísticas  Mis procesos  Estado de mi proceso
Estado de mi proceso
« Volver a mis procesos
Analista de ciberseguridad
Ajuste a la oferta 45 %
CONFIAR
 Eliminar postulación
Oferta publicada
23 Nov. - 2026
Postulación a
oferta
24 Nov. - 2026
Siguiente
35
Postulados"""

GUPY = {"results": [
    {"applicationId": 779033506, "applicationStatus": "in_process", "jobName": "Help Desk Analyst L2", "jobStatus": "published",
     "jobStepCount": 5, "jobStepCurrent": 1, "careerPageName": "Stefanini Latam"},
    {"applicationId": 778760473, "applicationStatus": "in_process", "jobName": "Analista de Soporte en Sitio", "jobStatus": "frozen",
     "jobStepCount": 5, "jobStepCurrent": 2, "careerPageName": "Stefanini Latam"},
    {"applicationId": 1, "applicationStatus": "reproved", "jobName": "QA Automation", "jobStepCount": 5, "jobStepCurrent": 1,
     "careerPageName": "Stefanini Latam"},
]}

MAGNETO = {"rows": [{"id": 1142698, "title": "Analista Riesgo", "companyName": "Confidencial", "statusName": "Aplicación enviada",
                     "statusId": 2},
                    {"id": 7, "title": "Aprendiz de sistemas", "companyName": "Comfama", "statusName": "Hoja de vida vista", "statusId": 3}]}

AIRA_ROWS = [["", "Oferta", "Empresa", "Fecha postulación", "Estado", "Acciones"],
             ["", "DATA ANALYST", "Seguros Falabella Colombia", "23-11-2026", "Pendiente información", "VER delete"],
             ["", "IT Support", "Falabella.com", "23-11-2026", "No seleccionado", "VER delete"], [""]]


def test_computrabajo_cards():
    seen = sg.parse_computrabajo(CT_ITEMS)
    assert [(s.title, s.company, s.status, s.level) for s in seen] == [
        ("Desarrollador de software", "Importante empresa del sector", "HdV Vista", sg.SEEN),
        ("Practicante de Proyectos / Calidad / Desarrollo", "", "HdV Vista", sg.SEEN),
        ("Auxiliar de sistemas", "CONTACTAMOS OUTSOURCING S.A.S.", "Postulado", sg.SENT)]
    assert seen[0].key == "A2AAFEC86E8E75D0DE47860191DDD917"


def test_elempleo_step_is_the_last_dated_one():
    assert sg.elempleo_step(EE_DETAIL) == "Postulación a oferta"
    seen = sg.parse_elempleo([{"id": "586995908", "offer": "1886801860", "title": "Analista de ciberseguridad", "company": "CONFIAR",
                               "step": "Postulación a oferta"},
                              {"id": "2", "offer": "3", "title": "Analista", "company": "X", "step": "Hoja de vida vista"}])
    assert [(s.level, s.ref) for s in seen] == [(sg.SENT, "ee:1886801860"), (sg.SEEN, "ee:3")]


def test_gupy_magneto_and_aira():
    gupy = sg.parse_gupy(GUPY)
    assert [(s.key, s.status, s.level) for s in gupy] == [
        ("779033506", "paso 1 de 5", sg.SENT), ("778760473", "paso 2 de 5", sg.ADVANCE), ("1", "reproved", sg.CLOSED)]
    magneto = sg.parse_magneto(MAGNETO)
    assert [(s.level, s.ref) for s in magneto] == [(sg.SENT, "mg:1142698"), (sg.SEEN, "mg:7")]
    aira = sg.parse_aira(AIRA_ROWS)
    assert [(s.title, s.level) for s in aira] == [("DATA ANALYST", sg.SENT), ("IT Support", sg.CLOSED)]


def test_only_new_statuses_are_news():
    seen = sg.parse_computrabajo(CT_ITEMS)
    changes, saved = sg.compare({}, seen, now="2026-11-24T20:00")
    assert [s.title for s, _ in changes] == ["Desarrollador de software", "Practicante de Proyectos / Calidad / Desarrollo"]
    assert len(saved) == 3  # también se guarda lo enviado, para notar cuando cambie
    again, _ = sg.compare(saved, seen)
    assert again == []  # nada nuevo, nada que avisar
    later = [sg.Seen("computrabajo", "C1", "Auxiliar de sistemas", "", "Finalista", sg.ADVANCE)]
    news, _ = sg.compare(saved, later)
    assert news[0][1]["status"] == "Postulado" and "Finalista" in sg.notice(news)


class FakeApi:
    def __init__(self):
        self.calls = []

    def post(self, path, body):
        self.calls.append((path, body))


def test_the_app_moves_forward_only_and_only_when_it_knows_which_one():
    apps = [{"id": 1, "role": "Desarrollador de Software", "company": "Importante empresa del sector", "status": "postulada"},
            {"id": 2, "role": "Analista", "company": "X", "status": "entrevista"},
            {"id": 3, "role": "Help Desk Analyst N1", "company": "Stefanini", "status": "postulada"},
            {"id": 4, "role": "Help Desk Analyst N1", "company": "Stefanini", "status": "postulada"}]
    changes = [(sg.Seen("computrabajo", "a", "Desarrollador de software", "Importante empresa del sector", "HdV Vista", sg.SEEN), None),
               (sg.Seen("elempleo", "b", "Otro título", "X", "Hoja de vida vista", sg.SEEN, ref="ee:9"), None),
               (sg.Seen("gupy", "c", "Help Desk Analyst N1", "Stefanini Latam", "paso 2 de 5", sg.ADVANCE), None)]
    api = FakeApi()
    assert sg.update_app(api, changes, apps, {"ee:9": 2}) == 1
    assert api.calls == [("/applications/1/status", {"status": "en_revision", "note": "Computrabajo: HdV Vista"}),
                         ("/applications/2/notes", {"note": "elempleo: Hoja de vida vista"})]  # ya en entrevista: solo nota
    # las dos «Help Desk Analyst N1» son iguales: no se adivina cuál avanzó (solo se avisa)
