from config import SKILL_CATEGORIES
from ui.tab_habilidades import _categories_for


class TestSkillCategories:
    def test_keeps_legacy_categories_so_old_skills_stay_visible(self):
        categories = _categories_for(["Lenguajes de Programación", "Herramientas y software"])
        assert categories[: len(SKILL_CATEGORIES)] == SKILL_CATEGORIES
        assert "Lenguajes de Programación" in categories
        assert categories.count("Herramientas y software") == 1

    def test_universal_categories_without_skills(self):
        assert _categories_for([]) == SKILL_CATEGORIES
