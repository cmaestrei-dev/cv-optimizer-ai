"""Casos de evaluación del motor de CV: perfiles y vacantes FICTICIOS con resultados esperados.

`expected` mapea una palabra que debe aparecer en el texto de un requisito de la vacante al conjunto
de niveles aceptables ("cubre", "parcial", "no"). Así se mide si el match acierta, sin depender de
cómo la IA redacte cada requisito.
"""

from dataclasses import dataclass, field

from core.profile.periods import parse_period
from core.profile.snapshot import AchievementSnap as A
from core.profile.snapshot import EducationSnap as Ed
from core.profile.snapshot import ExperienceSnap as X
from core.profile.snapshot import ProfileSnapshot
from core.profile.snapshot import SkillSnap as S
from models import UserProfile


def _p(text: str):
    return parse_period(text)


PROFILES: dict[str, tuple[ProfileSnapshot, UserProfile]] = {
    "laura_admin": (
        ProfileSnapshot(
            "laura", "Laura Gómez",
            experiences=(
                X(1, "Asistente Administrativa", "Concesionario Autos del Caribe", "Marzo 2023 - Presente", _p("Marzo 2023 - Presente"), "Colombia", "Presencial", (
                    A(11, "Elaboré y radiqué la facturación de ventas de vehículos y repuestos, con un promedio de 180 facturas al mes"),
                    A(12, "Concilié las cuentas por cobrar con el área de cartera y hice seguimiento a clientes morosos"),
                    A(13, "Organicé el archivo físico y digital de contratos y soportes contables"),
                    A(14, "Atendí a clientes en recepción y agendé citas del taller"),
                    A(15, "Preparé informes semanales de ventas en Excel con tablas dinámicas para la gerencia"),
                )),
                X(2, "Auxiliar Administrativa", "TiendaYa (e-commerce)", "Enero 2021 - Febrero 2023", _p("Enero 2021 - Febrero 2023"), "Colombia", "Híbrido", (
                    A(21, "Gestioné órdenes de compra y despachos con transportadoras"),
                    A(22, "Respondí devoluciones y PQR de clientes por correo y WhatsApp"),
                    A(23, "Llevé el control de inventario de bodega en hojas de cálculo"),
                    A(24, "Apoyé el pago a proveedores y la relación de facturas recibidas"),
                )),
                X(3, "Cajera", "Supermercado El Ahorro", "2019 - 2020", _p("2019 - 2020"), "Colombia", "Presencial", (
                    A(31, "Manejé caja y cuadre diario de efectivo"),
                )),
            ),
            skills=(S(1, "Excel", "Herramientas y software"), S(2, "Tablas dinámicas", "Herramientas y software"),
                    S(3, "Facturación", "Conocimientos del área"), S(4, "Cartera", "Conocimientos del área"),
                    S(5, "Atención al cliente", "Habilidades blandas"), S(6, "Inventarios", "Procesos y metodologías")),
            education=(Ed(1, "Tecnóloga en Gestión Administrativa", "SENA", "2018 - 2020", _p("2018 - 2020")),
                       Ed(2, "Curso de Excel intermedio", "Platzi", "2022", _p("2022"))),
        ),
        UserProfile(username="laura", full_name="Laura Gómez", email="laura@example.com"),
    ),
    "andres_dev": (
        ProfileSnapshot(
            "andres", "Andrés Ruiz",
            experiences=(
                X(1, "Desarrollador Backend Junior", "PagoFácil Fintech", "Febrero 2024 - Presente", _p("Febrero 2024 - Presente"), "Colombia", "Remoto", (
                    A(11, "Desarrollé APIs REST en Python con FastAPI para el módulo de pagos"),
                    A(12, "Escribí pruebas unitarias con pytest alcanzando 80% de cobertura"),
                    A(13, "Optimicé consultas SQL en PostgreSQL reduciendo el tiempo de respuesta de 2 s a 400 ms"),
                    A(14, "Empaqueté los servicios en contenedores Docker para el entorno de pruebas"),
                )),
                X(2, "Practicante de Desarrollo", "Agencia Pixel", "Enero 2023 - Diciembre 2023", _p("Enero 2023 - Diciembre 2023"), "Colombia", "Híbrido", (
                    A(21, "Mantuve sitios web en WordPress y PHP para 12 clientes"),
                    A(22, "Automaticé reportes semanales con Python y Google Sheets"),
                )),
            ),
            skills=(S(1, "Python", "Herramientas y software"), S(2, "FastAPI", "Herramientas y software"),
                    S(3, "PostgreSQL", "Herramientas y software"), S(4, "Git", "Herramientas y software"),
                    S(5, "Docker", "Herramientas y software"), S(6, "pytest", "Herramientas y software"),
                    S(7, "Inglés B1", "Idiomas")),
            education=(Ed(1, "Ingeniería de Sistemas", "Universidad del Norte", "2019 - 2024", _p("2019 - 2024")),),
        ),
        UserProfile(username="andres", full_name="Andrés Ruiz", email="andres@example.com"),
    ),
    "sofia_ventas": (
        ProfileSnapshot(
            "sofia", "Sofía Pérez",
            experiences=(
                X(1, "Asesora Comercial", "CeluMundo", "Junio 2022 - Presente", _p("Junio 2022 - Presente"), "Colombia", "Presencial", (
                    A(11, "Superé la meta de ventas mensual en 6 de los últimos 12 meses"),
                    A(12, "Atendí un promedio de 25 clientes diarios en punto de venta"),
                    A(13, "Manejé caja y arqueos diarios"),
                )),
                X(2, "Auxiliar de Servicio al Cliente", "ContactoTotal Call Center", "2020 - 2022", _p("2020 - 2022"), "Colombia", "Presencial", (
                    A(21, "Resolví reclamaciones telefónicas de clientes de telefonía"),
                    A(22, "Registré y di seguimiento a casos en Salesforce"),
                )),
            ),
            skills=(S(1, "Ventas", "Conocimientos del área"), S(2, "Atención al cliente", "Habilidades blandas"),
                    S(3, "Salesforce", "Herramientas y software"), S(4, "Negociación", "Habilidades blandas")),
            education=(Ed(1, "Técnica en Ventas", "SENA", "2018 - 2019", _p("2018 - 2019")),),
        ),
        UserProfile(username="sofia", full_name="Sofía Pérez", email="sofia@example.com"),
    ),
}


@dataclass
class Case:
    name: str
    profile: str
    vacancy: str
    language: str
    expected: dict[str, set[str]] = field(default_factory=dict)


CASES = [
    Case("admin_buen_match", "laura_admin", """Auxiliar Administrativo(a) - Logística Andina S.A.S. (Barranquilla, presencial)
Requisitos: técnico o tecnólogo en gestión administrativa; mínimo 2 años de experiencia en facturación y manejo
de cartera; Excel intermedio (tablas dinámicas, BUSCARV). Deseable: manejo de SAP Business One.
Funciones: elaborar facturas, conciliar cuentas por cobrar, archivar soportes contables, atender proveedores.""",
         "es", {"SAP": {"no"}, "Excel": {"cubre", "parcial"}, "factura": {"cubre"}, "gesti": {"cubre"}}),
    Case("admin_con_brechas", "laura_admin", """Analista Contable Junior - Grupo Costa
Requisitos obligatorios: contador público titulado; experiencia en SAP FI; conocimiento en NIIF;
manejo de conciliaciones bancarias. Deseable: inglés intermedio.
Funciones: registrar asientos contables, preparar conciliaciones, apoyar cierres mensuales.""",
         "es", {"SAP": {"no"}, "NIIF": {"no"}, "contador": {"no"}, "ingl": {"no"}}),
    Case("dev_backend", "andres_dev", """Desarrollador Backend (Python) - TechAndes, remoto
Requisitos: 1+ año de experiencia con Python; FastAPI o Django; PostgreSQL; Docker; pruebas automatizadas.
Deseable: AWS, Kubernetes.
Funciones: construir APIs, optimizar consultas, escribir pruebas.""",
         "es", {"Python": {"cubre"}, "PostgreSQL": {"cubre"}, "Docker": {"cubre"}, "AWS": {"no"}, "Kubernetes": {"no"}}),
    Case("dev_en_ingles", "andres_dev", """Junior Python Developer - NorthBridge Software (Remote, LATAM)
Requirements: Python; REST APIs; SQL databases; Git; English B2 or higher.
Nice to have: GraphQL.
Responsibilities: build and maintain backend services, write tests, collaborate with a US-based team.""",
         "en", {"Python": {"cubre"}, "Git": {"cubre"}, "English": {"parcial", "no"}, "GraphQL": {"no"}}),
    Case("ventas", "sofia_ventas", """Asesor(a) Comercial - Motos del Norte (Barranquilla)
Requisitos: experiencia mínima de 1 año en ventas y cumplimiento de metas; atención al cliente; manejo de CRM;
licencia de conducción B1 vigente.
Funciones: asesorar clientes, cerrar ventas, registrar oportunidades en el CRM.""",
         "es", {"venta": {"cubre"}, "CRM": {"cubre", "parcial"}, "licencia": {"no"}}),
]
