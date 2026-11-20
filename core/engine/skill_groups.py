"""Agrupar habilidades técnicas como se espera en un CV de tecnología (lenguajes, frameworks, bases de datos…).

Solo reordena lo que la persona YA tiene en su perfil, y solo las que guardó en una categoría genérica
(«Herramientas y software», «Otros»): nunca agrega ni renombra habilidades. Cualquier otra profesión queda igual.
"""

from core.profile.repository import skill_key

LANGUAGES = "Lenguajes de Programación"
FRAMEWORKS = "Frameworks / Librerías"
DATABASES = "Bases de Datos"
DEVOPS = "Nube y DevOps"
SECURITY = "Ciberseguridad"
DATA = "Datos y analítica"

_GENERIC = {"Herramientas y software", "Otros", "Otras"}

_TECH: dict[str, set[str]] = {
    LANGUAGES: {"python", "java", "javascript", "typescript", "c#", "c/c++", "c++", "c", "ruby", "r", "dart", "go",
                "golang", "kotlin", "swift", "php", "sql", "bash", "rust", "scala", "html", "css", "html/css"},
    FRAMEWORKS: {"fastapi", "react", "react.js", "reactjs", "next.js", "nextjs", "node.js", "nodejs", "express",
                 "django", "flask", "ruby on rails", "rails", "flutter", "angular", "vue", "vue.js", "spring",
                 "spring boot", ".net", "laravel", "tailwind", "tailwind css", "prisma", "sqlalchemy", "pydantic",
                 "bloc", "react native", "jquery", "bootstrap"},
    DATABASES: {"postgresql", "postgres", "mysql", "mongodb", "sqlite", "microsoft sql server", "sql server", "redis",
                "oracle", "firebase", "dynamodb", "mariadb", "supabase"},
    DEVOPS: {"docker", "kubernetes", "aws", "amazon web services", "amazon web services (aws)", "aws lambda", "s3",
             "gcp", "google cloud", "azure", "git", "github", "github actions", "ci/cd", "linux", "terraform",
             "vercel", "cloudflare", "nginx", "cloud run", "heroku"},
    SECURITY: {"nmap", "shodan", "siem", "wireshark", "burp suite", "metasploit", "owasp", "kali linux",
               "seguridad de redes", "pentesting", "hardening"},
    DATA: {"pandas", "numpy", "matplotlib", "power bi", "tableau", "jupyter notebooks", "jupyter", "scikit-learn",
           "excel avanzado", "web scraping", "analisis exploratorio de datos (eda)", "etl"},
}
_LOOKUP = {skill_key(name): group for group, names in _TECH.items() for name in names}


def vocabulary() -> set[str]:
    """Todos los nombres técnicos conocidos (para verificar que el CV no afirme uno que la persona no tiene)."""
    return {name for names in _TECH.values() for name in names}
ORDER = [LANGUAGES, FRAMEWORKS, DATABASES, DEVOPS, SECURITY, DATA]
LABELS_EN = {LANGUAGES: "Programming languages", FRAMEWORKS: "Frameworks & libraries", DATABASES: "Databases",
             DEVOPS: "Cloud & DevOps", SECURITY: "Cybersecurity", DATA: "Data & analytics"}


def display_category(name: str, category: str) -> str:
    """Categoría con la que se muestra en el CV."""
    if category in _GENERIC:
        return _LOOKUP.get(skill_key(name), category)
    return category
