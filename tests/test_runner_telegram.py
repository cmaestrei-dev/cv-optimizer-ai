"""Bot de Telegram del dueño: emparejar, solo atender su chat, pausar y responder preguntas (sin red)."""

import json
from datetime import UTC, datetime

import pytest

from runner import __main__ as cli
from runner import config as cfg
from runner import telegram
from runner.state import State


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram, "TOKEN_FILE", tmp_path / "telegram")
    monkeypatch.setattr(telegram, "CHAT_FILE", tmp_path / "telegram_chat")
    monkeypatch.setattr(telegram, "CONTROL_FILE", tmp_path / "control.json")
    monkeypatch.setattr(telegram, "EXTRA_ANSWERS", tmp_path / "extra.json")
    monkeypatch.setattr(cfg, "EXTRA_ANSWERS_FILE", tmp_path / "extra.json")
    monkeypatch.setattr(telegram, "_bank", lambda: {"aspiracion salarial": "3000000"})
    return tmp_path


class FakeClient:
    def __init__(self, batches):
        self.batches, self.sent, self.calls = list(batches), [], []

    def updates(self, offset, wait=50):
        return self.batches.pop(0) if self.batches else []

    def call(self, method, **params):
        self.calls.append(method)

    def send(self, chat, text):
        self.sent.append((chat, text))


def msg(update_id, chat, text, kind="private"):
    return {"update_id": update_id, "message": {"chat": {"id": chat, "type": kind}, "text": text}}


def test_token_is_validated_and_private(files):
    with pytest.raises(telegram.TelegramError):
        telegram.save_token("no-es-un-token")
    telegram.save_token("  123456789:" + "A" * 35 + "  ")
    assert telegram.token() == "123456789:" + "A" * 35
    assert (files / "telegram").stat().st_mode & 0o777 == 0o600


def test_pairing_needs_the_one_time_code_in_a_private_chat(files):
    client = FakeClient([[msg(1, 555, "/start 000000"), msg(2, 777, "/start 123456", kind="group")],
                         [msg(3, 999, "/start 123456")]])
    assert telegram.pair(client, "123456", minutes=1) == 999
    assert telegram.chat_id() == 999 and (files / "telegram_chat").stat().st_mode & 0o777 == 0o600


def test_only_the_paired_chat_is_answered(files, tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    client = FakeClient([[msg(1, 111, "/estado"), msg(2, 999, "/ayuda")]])
    telegram.serve(client, 999, once=True)
    assert [chat for chat, _ in client.sent] == [999] and "/preguntas" in client.sent[0][1]


def state_with_skipped(tmp_path) -> State:
    state = State(tmp_path / "estado.json")
    state.mark("ct:A", "saltada", portal="computrabajo", app=1, url="u1", cv="/x/cv.pdf", cv_id=7, puntaje=80,
               preguntas=["¿Has firmado contrato de aprendizaje?", "¿Cuál es tu aspiración salarial?"])
    state.mark("mg:9", "saltada", portal="magneto", app=2, url="u2", preguntas=["¿Has firmado contrato de aprendizaje?"])
    return state


def test_questions_are_listed_once_and_answers_go_to_the_extra_bank(files, tmp_path):
    state = state_with_skipped(tmp_path)
    reply, listed = telegram.handle("/preguntas", state, [])
    assert listed == ["¿Has firmado contrato de aprendizaje?"]  # la de salario ya está en el banco; sin repetir
    reply, _ = telegram.handle("/responder 1 No, nunca", state, listed)
    assert "Guardado" in reply
    saved = json.loads((files / "extra.json").read_text())
    assert saved == {"has firmado contrato de aprendizaje": "No, nunca"}
    assert telegram.handle("/responder 5 algo", state, listed)[0].startswith("Ese número no está")
    assert telegram.pending_questions(state) == []


def test_answered_skips_go_back_to_the_queue(files, tmp_path):
    state = state_with_skipped(tmp_path)
    conf = cfg.Config(api="https://x", token="t", answers={"aspiracion salarial": "3000000",
                                                         "has firmado contrato de aprendizaje": "No"})
    assert cli._retry_answered(state, conf) == 1  # la de Magneto no tenía CV guardado: no se puede reintentar
    assert state.data["vistas"]["ct:A"]["estado"] == "preparada" and state.data["vistas"]["ct:A"]["cv_id"] == 7
    assert state.data["vistas"]["mg:9"]["estado"] == "saltada"


def test_pause_and_resume_from_the_phone(files, tmp_path):
    reply, _ = telegram.handle("/pausar 5", State(tmp_path / "e.json"), [])
    until = telegram.paused_until()
    assert until and until > datetime.now(UTC) and "no corro vueltas" in reply
    telegram.handle("/reanudar", State(tmp_path / "e.json"), [])
    assert telegram.paused_until() is None


def test_extra_answers_join_the_bank_when_loading_the_config(files, tmp_path, monkeypatch):
    monkeypatch.setenv("CVO_BOT_TOKEN", "cvb_x")
    (files / "extra.json").write_text(json.dumps({"has firmado contrato de aprendizaje": "No"}))
    path = tmp_path / "config.toml"
    path.write_text(cfg.TEMPLATE.replace("https://TU-SERVICIO.run.app/api", "https://app.example.com/api"), encoding="utf-8")
    assert cfg.load(path).answers["has firmado contrato de aprendizaje"] == "No"


def test_listener_unit_runs_from_a_stable_copy(tmp_path):
    from runner import schedule

    unit = schedule.listener_unit("/usr/bin/python3", tmp_path / "codigo", tmp_path / "telegram.log")
    assert "ExecStart=/usr/bin/python3 -m runner telegram escuchar" in unit and "Restart=always" in unit
    with pytest.raises(schedule.ScheduleError):
        schedule.listener_unit("/usr/bin/python3", tmp_path / ".claude/worktrees/x", tmp_path / "t.log")


def test_experience_questions_count_as_answered_in_si_mode(files, tmp_path):
    state = State(tmp_path / "estado.json")
    state.mark("mg:1", "saltada", portal="magneto", app=1, url="u", cv="/x.pdf", cv_id=3,
               preguntas=["¿Tiene experiencia en administración de servicios web?", "Vive en Bogotá"])
    conf = cfg.Config(api="https://x", token="t", no_evidence="si", answers={"vive en": "No, vivo en Cartagena."})
    assert cli._retry_answered(state, conf) == 1
    conf = cfg.Config(api="https://x", token="t", no_evidence="saltar", answers={"vive en": "No, vivo en Cartagena."})
    state.mark("mg:1", "saltada", portal="magneto", app=1, url="u", cv="/x.pdf", cv_id=3,
               preguntas=["¿Tiene experiencia en administración de servicios web?"])
    assert cli._retry_answered(state, conf) == 0
