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
    assert answers.to_integer("2,5 años") == "2"
    assert answers.to_integer("Tengo 1 año de experiencia") == "1"
    assert answers.to_integer("") is None and answers.to_integer("varios") is None


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
