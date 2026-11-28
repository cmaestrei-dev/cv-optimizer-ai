from runner import answers

BANK = {"aspiracion salarial|salario|salary": "3000000", "nivel de ingles|english": "A2", "practica|internship": "Sí"}


def test_bank_matches_patterns_without_accents():
    assert answers.bank_answer("¿Cuál es tu aspiración salarial mensual?", BANK) == "3000000"
    assert answers.bank_answer("What is your English level?", BANK) == "A2"
    assert answers.bank_answer("¿Estás disponible para realizar práctica empresarial?", BANK) == "Sí"
    assert answers.bank_answer("¿Cuántos años de experiencia tienes con Python?", BANK) is None


def test_years_questions():
    assert answers.is_years("¿Cuántos años de experiencia tienes con Python?*")
    assert answers.is_years("How many years of work experience do you have with React?")
    assert answers.is_years("¿Cuánto tiempo de experiencia tienes en desarrollo Backend o Full Stack?")
    assert not answers.is_years("¿Tienes experiencia con Python?")
    assert not answers.is_years("¿Cuánto tiempo te toma llegar a la oficina?")


def test_integers_round_down():
    assert answers.to_integer("2,5 años") == "3"  # hacia arriba (decisión del dueño, 2026-11-27)
    assert answers.to_integer("Tengo 1 año de experiencia") == "1"
    assert answers.to_integer("") is None and answers.to_integer("varios") is None


def test_periods_never_turn_months_into_years():
    # Caso real (2026-11-24): «4 meses en Equimat» salía como «4 años»; «11 meses en Karta», como «11 años».
    assert answers.to_period("4 meses (Equimat Solutions)") == "1"
    assert answers.to_period("Tengo 11 meses de experiencia en Karta") == "1"
    assert answers.to_period("18 meses") == "2" and answers.to_period("2 años") == "2" and answers.to_period("1,5 años") == "2"
    assert answers.to_period("0 años") == "0" and answers.to_period("12 meses") == "1"  # lo exacto no sube
    assert answers.to_period("1 año", months=True) == "12" and answers.to_period("4 meses", months=True) == "4"
    assert answers.to_period("3") == "3" and answers.to_period("ninguna") is None


def test_pick_option():
    assert answers.pick_option("Sí", ["Selecciona una opción", "Sí", "No"]) == "Sí"
    assert answers.pick_option("Yes", ["Select an option", "Yes", "No"]) == "Yes"
    assert answers.pick_option("No", ["Sí", "No"]) == "No"
    assert answers.pick_option("A2", ["Básico", "A2 - Básico", "B1"]) == "A2 - Básico"
    assert answers.pick_option("Inmediata", ["En 15 días", "Inmediata"]) == "Inmediata"
    assert answers.pick_option("Sí", ["Selecciona una opción", "Tal vez"]) is None
    assert answers.pick_option("", ["Sí"]) is None


def test_asks_experience():
    assert answers.asks_experience("¿Qué experiencia tienes con Microsoft Azure y herramientas DevOps?")
    assert answers.asks_experience("¿Tiene algún conocimiento en contenedores Docker?")
    assert not answers.asks_experience("¿Cuál es tu nivel de formación académica?")
    assert not answers.asks_experience("¿Cuál es tu dirección y localidad?")


def test_years_options_pick_the_range_that_contains_them():
    options = ["Selecciona una opción", "Menos de 1 año", "1 a 2 años", "3 a 5 años", "Más de 5 años"]
    assert answers.pick_option("2", options) == "1 a 2 años"
    assert answers.pick_option("0", options) == "Menos de 1 año"
    assert answers.pick_option("7", options) == "Más de 5 años"
    assert answers.pick_years(2, ["0-1", "1-3", "3-5", "5+"]) == "1-3"
    assert answers.pick_years(2, ["Ninguna", "6 meses", "1 año", "3 años"]) == "1 año"  # ninguna la contiene: la más cercana (empate: la menor)
    assert answers.pick_option("1", ["Sí", "No"]) == "Sí"  # sin números en las opciones, sigue siendo sí/no


def test_months_questions():
    assert answers.asks_months("¿Cuántos meses de experiencia tienes en ventas?")
    assert not answers.asks_months("¿Cuántos años de experiencia tienes con Python?")


def test_yes_no_options_with_more_words():
    # Magneto (2026-11-21): «Sí, tengo experiencia en…» / «No tengo experiencia…»
    options = ["Sí, tengo experiencia en administración de servicios web.", "No tengo experiencia, pero estoy interesado.",
               "He trabajado en soporte técnico."]
    assert answers.pick_option("Sí", options) == options[0]
    assert answers.pick_option("No", options) == options[1]
    assert answers.pick_option("No, vivo en Cartagena de Indias y puedo trasladarme.", ["Si", "No"]) == "No"
    assert answers.pick_option("Sí, vivo en Cartagena.", ["Si", "No"]) == "Si"


def test_options_match_by_word_stem():
    levels = ["Bachiller", "Técnico", "Universitaria", "Posgrado"]
    assert answers.pick_option("Universitario en curso", levels) == "Universitaria"
    assert answers.pick_option("Algo que no se parece", levels) is None


def test_favorable_option_for_experience_questions():
    assert answers.favorable_option(["No", "Sí, más de un año"]) == "Sí, más de un año"
    assert answers.favorable_option(["Ninguno", "Básico", "Intermedio", "Avanzado"]) == "Intermedio"
    assert answers.favorable_option(["Ninguno", "Básico", "Avanzado"]) == "Avanzado"
    assert answers.favorable_option(["No tengo", "Ninguna"]) is None
    assert answers.negative("No, nunca") and not answers.negative("Nociones básicas")


def test_experience_questions_with_typos():
    assert answers.asks_experience("¿haz tenido experiencien administrando infraestructura Cloud, AWS?")
    assert answers.asks_experience("Do you have experience with Docker?")
    assert not answers.asks_experience("¿Es mayor de edad?")



def test_expected_salary_follows_the_vacancy():
    # Decisión del dueño (2026-11-22): según la vacante; sin cifra publicada, 3 millones; en prácticas, sin cifra.
    from runner.answers import asks_expected_salary, expected_salary

    assert asks_expected_salary("¿Cuál es tu aspiración salarial?") and asks_expected_salary("Indícanos tu expectativa salarial")
    assert not asks_expected_salary("¿Cuál es tu salario actual?") and not asks_expected_salary("¿Último salario?")
    assert expected_salary("Salario: $2.500.000 - $3.500.000 COP", "Desarrollador Junior") == 3_000_000  # punto medio
    assert expected_salary("Rango salarial entre 2,8 y 3,4 millones", "Analista") == 3_100_000
    assert expected_salary("Salario 2800000 + prestaciones", "Analista") == 2_800_000
    assert expected_salary("Somos 300 personas desde 2015; 11.000.000 de transacciones; tel 3001234567", "Dev") == 3_000_000
    assert expected_salary("Auxilio de transporte $200.000", "Soporte") == 3_000_000  # no es un sueldo
    assert expected_salary("", "Practicante de Sistemas") is None


def test_salary_question_with_a_typo():
    # Caso real (Computrabajo, 2026-11-24): «cual seria tu aspiracion salaria».
    assert answers.asks_expected_salary("cual seria tu aspiracion salaria")
    assert not answers.asks_expected_salary("¿Cuál es tu salario actual?")


def test_language_levels_map_to_the_forms_words():
    softtek = ["Básico", "Intermedio", "Intermedio alto", "Avanzado", "Fluent", "Native / Bilingual"]
    assert answers.pick_option("A2", softtek) == "Básico" and answers.pick_option("B1", softtek) == "Intermedio"
    assert answers.pick_option("B2", softtek) == "Intermedio alto" and answers.pick_option("C1", softtek) == "Avanzado"
    assert answers.pick_option("A2", ["A1", "A2", "B1"]) == "A2"  # si el formulario usa el marco europeo, tal cual


def test_real_options_that_were_skipped_on_2026_11_28():
    # Vuelta del 28-11: cuatro vacantes de Computrabajo saltadas porque la respuesta no calzaba con las opciones.
    security = ["0-6 meses", "6-12 meses", "1-3 años", "3-5 años", "más de 5 años"]
    assert answers.pick_option("Más de 1 año", security) == "1-3 años"
    assert answers.pick_option("1 año", security) == "1-3 años"  # en el borde, el mayor: se redondea hacia arriba
    assert answers.pick_option("4 meses", security) == "0-6 meses"
    audit = ["4 años o mas", "De 1 a 3 años", "Tengo experiencia en sistemas e informática pero no en auditoria, con…"]
    assert answers.pick_option("1 año", audit) == "De 1 a 3 años"
    assert answers.pick_option("Cartagena de Indias, Bolívar, Colombia", ["Cali", "Palmira", "Jamundí", "Otra"]) == "Otra"
    assert answers.pick_option("Cali", ["Cali", "Palmira", "Otra"]) == "Cali"
    assert answers.pick_option("Sí", ["Cali", "Otra"]) is None  # un sí/no nunca cae en «Otra»
    assert answers.pick_option("Cartagena", ["Cali", "Otra", "Otro municipio"]) is None  # dos «otra»: no se adivina
    assert answers.pick_years(1, ["0-1", "1-3", "3-5"]) == "1-3"
    assert answers.pick_years(2, ["12 a 24 meses", "Más de 24 meses"]) == "12 a 24 meses"  # «más de» no incluye el borde
    assert answers.pick_option("5 años", audit) == "4 años o mas"


def test_internship_period_is_the_nearest_to_today():
    # El dueño (2026-11-28): puede hacer prácticas desde ya; «coloca la que esté más cerca del tiempo actual».
    from datetime import date

    assert answers.nearest_period(["2026 I", "2026II"], date(2026, 11, 28)) == "2026II"  # caso real de Grupo emi
    assert answers.nearest_period(["2026 II", "2027 I", "2027 II"], date(2027, 1, 15)) == "2027 I"
    assert answers.nearest_period(["Primer semestre 2027", "Segundo semestre 2027"], date(2026, 11, 28)) == "Primer semestre 2027"
    assert answers.nearest_period(["2027-1", "2026-2"], date(2026, 8, 1)) == "2026-2"
    assert answers.nearest_period(["2025 I", "2025 II"], date(2026, 11, 28)) == "2025 II"  # todas pasaron: la última
    assert answers.nearest_period(["Sí", "No"], date(2026, 11, 28)) is None
    assert answers.pick_option("Desde ya: el periodo más cercano", ["2099 II", "2099 I"]) == "2099 I"
    assert answers.pick_option("Desde ya: el periodo más cercano", ["Sí", "No"]) is None
    assert answers.pick_option("Bueno", ["Sí", "No"]) is None  # antes: «No», porque «no» está dentro de «bueno»
    owner = "Sí, desde ya: el periodo más cercano"  # el valor del banco del dueño
    assert answers.pick_option(owner, ["Sí", "No"]) == "Sí" and answers.pick_option(owner, ["2099 I", "2099 II"]) == "2099 I"
