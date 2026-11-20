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
    assert not answers.is_years("¿Tienes experiencia con Python?")


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
