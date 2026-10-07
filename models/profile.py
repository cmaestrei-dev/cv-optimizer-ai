import hashlib
import hmac
import html
import os
from dataclasses import dataclass


def _link_html(url: str) -> str:
    text = html.escape(url.replace("https://", "").replace("http://", ""))
    if ":" not in url:
        url = f"https://{url}"
    if not url.lower().startswith(("https://", "http://")):
        return text
    return f'<a href="{html.escape(url)}">{text}</a>'


@dataclass
class UserProfile:
    username: str
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    password_hash: str = ""
    salt: str = ""

    @property
    def slug(self) -> str:
        return self.username.lower().replace(" ", "_")

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash and self.salt)

    def set_password(self, password: str) -> None:
        self.salt = os.urandom(32).hex()
        self.password_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(self.salt), 600_000
        ).hex()

    def verify_password(self, password: str) -> bool:
        if not self.has_password:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(self.salt), 600_000
        ).hex()
        return hmac.compare_digest(candidate, self.password_hash)

    @property
    def contact_line_html(self) -> str:
        parts = []
        if self.email:
            email = html.escape(self.email)
            parts.append(f'<a href="mailto:{email}">{email}</a>')
        if self.phone:
            parts.append(html.escape(self.phone))
        if self.linkedin_url:
            parts.append(_link_html(self.linkedin_url))
        if self.github_url:
            parts.append(_link_html(self.github_url))
        return " | ".join(parts)

    @property
    def contact_line_text(self) -> str:
        parts = [self.email, self.phone, self.linkedin_url, self.github_url]
        return " | ".join(
            p.replace("https://", "").replace("http://", "") for p in parts if p
        )

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "linkedin_url": self.linkedin_url,
            "github_url": self.github_url,
            "password_hash": self.password_hash,
            "salt": self.salt,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        return cls(
            username=data.get("username", ""),
            full_name=data.get("full_name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            linkedin_url=data.get("linkedin_url", ""),
            github_url=data.get("github_url", ""),
            password_hash=data.get("password_hash", ""),
            salt=data.get("salt", ""),
        )
