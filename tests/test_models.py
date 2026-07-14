from models.profile import UserProfile


class TestUserProfile:
    def test_create_profile(self):
        profile = UserProfile(
            username="juan_perez",
            full_name="Juan Pérez",
            email="juan@email.com",
            phone="+57 300 123 4567",
        )
        assert profile.username == "juan_perez"
        assert profile.slug == "juan_perez"

    def test_slug_normalization(self):
        profile = UserProfile(username="Juan Perez")
        assert profile.slug == "juan_perez"

    def test_contact_line_full(self):
        profile = UserProfile(
            username="test",
            email="test@test.com",
            phone="123",
            linkedin_url="https://linkedin.com/in/test",
            github_url="https://github.com/test",
        )
        line = profile.contact_line_html
        assert "test@test.com" in line
        assert "123" in line
        assert "linkedin.com/in/test" in line
        assert "github.com/test" in line

    def test_contact_line_empty(self):
        profile = UserProfile(username="test")
        assert profile.contact_line_html == ""

    def test_to_dict_and_from_dict(self):
        original = UserProfile(
            username="juan",
            full_name="Juan Pérez",
            email="juan@email.com",
            phone="+57",
            linkedin_url="https://linkedin.com/in/juan",
            github_url="https://github.com/juan",
        )
        original.set_password("secure123")
        data = original.to_dict()
        restored = UserProfile.from_dict(data)
        assert restored.username == original.username
        assert restored.full_name == original.full_name
        assert restored.email == original.email
        assert restored.linkedin_url == original.linkedin_url
        assert restored.github_url == original.github_url
        assert restored.password_hash == original.password_hash
        assert restored.salt == original.salt
        assert restored.verify_password("secure123")

    def test_from_dict_legacy_no_password(self):
        legacy_data = {
            "username": "old_user",
            "full_name": "Old User",
            "email": "",
            "phone": "",
            "linkedin_url": "",
            "github_url": "",
        }
        restored = UserProfile.from_dict(legacy_data)
        assert restored.username == "old_user"
        assert not restored.has_password
        assert restored.password_hash == ""
        assert restored.salt == ""


class TestPasswordHashing:
    def test_set_and_verify_correct_password(self):
        profile = UserProfile(username="test")
        profile.set_password("my_secret")
        assert profile.has_password
        assert profile.verify_password("my_secret")

    def test_verify_wrong_password(self):
        profile = UserProfile(username="test")
        profile.set_password("my_secret")
        assert not profile.verify_password("wrong_password")

    def test_has_password_false_by_default(self):
        profile = UserProfile(username="test")
        assert not profile.has_password
        assert not profile.verify_password("anything")

    def test_different_salts_produce_different_hashes(self):
        a = UserProfile(username="a")
        b = UserProfile(username="b")
        a.set_password("same_password")
        b.set_password("same_password")
        assert a.salt != b.salt
        assert a.password_hash != b.password_hash
        assert a.verify_password("same_password")
        assert b.verify_password("same_password")

    def test_verify_empty_against_no_password(self):
        profile = UserProfile(username="test")
        assert not profile.verify_password("")

    def test_password_hash_not_in_contact_line(self):
        profile = UserProfile(
            username="test",
            email="test@test.com",
            phone="123",
        )
        profile.set_password("secret")
        html = profile.contact_line_html
        assert "test@test.com" in html
        assert "secret" not in html
        assert profile.password_hash not in html
