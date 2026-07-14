import pytest

from storage import (
    all_data_files_exist,
    append_skill,
    delete_education_entry,
    get_skills_lines,
    has_education,
    has_knowledge_base,
    has_skills,
    load_profile,
    overwrite_skills,
    prepend_education,
    prepend_knowledge_base,
    read_education,
    read_knowledge_base,
    save_profile,
)


@pytest.fixture(autouse=True)
def temp_data_dir(monkeypatch, tmp_path):
    test_data = str(tmp_path / "data")
    monkeypatch.setattr("config.DATA_DIR", test_data)
    monkeypatch.setattr("storage._db._inited", False)
    yield test_data


class TestProfileStorage:
    def test_save_and_load(self, temp_data_dir):
        data = {
            "username": "test_user",
            "full_name": "Test User",
            "email": "test@test.com",
            "phone": "123",
            "linkedin_url": "",
            "github_url": "",
        }
        save_profile("test_user", data)
        loaded = load_profile("test_user")
        assert loaded is not None
        assert loaded["username"] == "test_user"
        assert loaded["email"] == "test@test.com"

    def test_load_nonexistent(self, temp_data_dir):
        assert load_profile("nonexistent") is None


class TestKnowledgeBase:
    def test_read_empty(self, temp_data_dir):
        assert read_knowledge_base("user1") == ""

    def test_prepend_and_read(self, temp_data_dir):
        prepend_knowledge_base("user1", "Experiencia 1")
        prepend_knowledge_base("user1", "Experiencia 2")
        content = read_knowledge_base("user1")
        assert "Experiencia 2" in content
        assert "Experiencia 1" in content
        assert content.startswith("Experiencia 2")

    def test_has_knowledge_base(self, temp_data_dir):
        assert not has_knowledge_base("user1")
        prepend_knowledge_base("user1", "test")
        assert has_knowledge_base("user1")


class TestSkills:
    def test_append_and_read(self, temp_data_dir):
        assert get_skills_lines("user1") == []

        append_skill("user1", "- **Python** -> [Lenguajes de Programación]\n")
        append_skill("user1", "- **Docker** -> [Herramientas / DevOps]\n")

        lines = get_skills_lines("user1")
        assert len(lines) == 2
        assert "Python" in lines[0]
        assert "Docker" in lines[1]

    def test_overwrite(self, temp_data_dir):
        append_skill("user1", "- **A** -> [Otros]\n")
        overwrite_skills("user1", ["- **B** -> [Otros]\n"])
        lines = get_skills_lines("user1")
        assert len(lines) == 1
        assert "B" in lines[0]

    def test_has_skills(self, temp_data_dir):
        assert not has_skills("user1")
        append_skill("user1", "- **test** -> [Otros]\n")
        assert has_skills("user1")


class TestEducation:
    def test_read_empty(self, temp_data_dir):
        assert read_education("user1") == ""

    def test_prepend_and_read(self, temp_data_dir):
        prepend_education("user1", "### Title - School | 2022\n\n")
        prepend_education("user1", "### Title2 - School2 | 2023\n- Desc\n\n")
        content = read_education("user1")
        assert "Title2" in content
        assert "Title" in content
        assert content.startswith("### Title2")

    def test_delete_entry(self, temp_data_dir):
        prepend_education("user1", "### Entry1 - School1 | 2021\n\n")
        prepend_education("user1", "### Entry2 - School2 | 2022\n\n")
        prepend_education("user1", "### Entry3 - School3 | 2023\n\n")

        assert delete_education_entry("user1", 0)  # delete most recent
        content = read_education("user1")
        assert "Entry3" not in content
        assert "Entry2" in content
        assert "Entry1" in content

    def test_has_education(self, temp_data_dir):
        assert not has_education("user1")
        prepend_education("user1", "### Test\n\n")
        assert has_education("user1")


class TestAllDataFilesExist:
    def test_none_exist(self, temp_data_dir):
        assert not all_data_files_exist("user1")

    def test_all_exist(self, temp_data_dir):
        prepend_knowledge_base("user1", "test")
        append_skill("user1", "- **test** -> [Otros]\n")
        prepend_education("user1", "### Test\n\n")
        assert all_data_files_exist("user1")

    def test_partial(self, temp_data_dir):
        prepend_knowledge_base("user1", "test")
        assert not all_data_files_exist("user1")
