"""Programación del bot: archivos de systemd y la vuelta diaria (sin tocar el systemd real ni LinkedIn)."""

import argparse
from pathlib import Path

import pytest

from runner import __main__ as cli
from runner import config as cfg
from runner import schedule
from runner.state import State

PY = "/usr/bin/python3"


def test_unit_files_run_one_round_at_each_time(tmp_path):
    files = schedule.unit_files(PY, tmp_path / "codigo", ["15:47", "9:17"], tmp_path / "registro.log")
    service, timer = files["cv-optimizer-bot.service"], files["cv-optimizer-bot.timer"]
    assert f"ExecStart={PY} -m runner diario" in service
    assert f"WorkingDirectory={tmp_path / 'codigo'}" in service
    assert f"StandardOutput=append:{tmp_path / 'registro.log'}" in service
    assert timer.index("OnCalendar=*-*-* 09:17:00") < timer.index("OnCalendar=*-*-* 15:47:00")
    assert "Persistent=true" in timer and "WantedBy=timers.target" in timer


@pytest.mark.parametrize("times", [["25:00"], ["9"], []])
def test_invalid_times(times):
    with pytest.raises(schedule.ScheduleError):
        schedule.normalize_times(times)


@pytest.mark.parametrize("workdir", ["/home/x/mis proyectos/app", "/home/x/100%/app", "/r/.claude/worktrees/rama"])
def test_paths_systemd_would_misread_or_temporary_copies_are_rejected(tmp_path, workdir):
    with pytest.raises(schedule.ScheduleError):
        schedule.unit_files(PY, Path(workdir), ["09:17"], tmp_path / "registro.log")


def test_install_and_remove(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(schedule, "UNIT_DIR", tmp_path / "units")
    monkeypatch.setattr(schedule.shutil, "which", lambda _: "/usr/bin/systemctl")

    def run(cmd, **kwargs):
        calls.append(cmd[2:])
        out = "NEXT LEFT LAST PASSED UNIT ACTIVATES\nThu 09:17 10h - - cv-optimizer-bot.timer cv-optimizer-bot.service\n"
        return argparse.Namespace(returncode=0, stdout=out if "list-timers" in cmd else "", stderr="")

    monkeypatch.setattr(schedule.subprocess, "run", run)
    nxt = schedule.install(PY, tmp_path / "codigo", ["09:17"], tmp_path / "datos" / "registro.log")
    assert (tmp_path / "units" / "cv-optimizer-bot.timer").is_file() and "09:17" in nxt
    assert calls[:2] == [["daemon-reload"], ["enable", "--now", "cv-optimizer-bot.timer"]]
    schedule.remove()
    assert not (tmp_path / "units" / "cv-optimizer-bot.timer").exists()
    assert ["disable", "--now", "cv-optimizer-bot.timer"] in calls


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    notices = []
    monkeypatch.setattr(cli, "_notify", notices.append)
    return tmp_path, notices


def test_round_searches_then_applies_even_if_the_search_breaks(data_dir, monkeypatch, capsys):
    tmp_path, notices = data_dir
    order = []

    def buscar(_args):
        order.append("buscar")
        raise RuntimeError("LinkedIn cambió la página")

    def postular(_args):
        order.append("postular")
        state = State(tmp_path / "estado.json")
        state.count("enviadas")
        state.count("preparadas_computrabajo")
        state.save()
        return 0

    monkeypatch.setattr(cli, "cmd_buscar", buscar)
    monkeypatch.setattr(cli, "cmd_postular", postular)
    assert cli.cmd_diario(None) == 0
    assert order == ["buscar", "postular"]
    assert notices == ["Hoy: 1 enviadas y 0 preparadas. Computrabajo: 0 enviadas y 1 preparadas."]
    assert "RuntimeError" in capsys.readouterr().err


def test_round_warns_about_a_lost_session_and_a_paused_account(data_dir, monkeypatch):
    tmp_path, notices = data_dir
    monkeypatch.setattr(cli, "cmd_buscar", lambda _args: 0)

    def postular(_args):
        state = State(tmp_path / "estado.json")
        state.data["sesion_perdida"] = ["computrabajo"]
        state.save()
        return 1

    monkeypatch.setattr(cli, "cmd_postular", postular)
    cli.cmd_diario(None)
    assert "perdió la sesión de Computrabajo: python -m runner entrar computrabajo" in notices[-1]
    state = State(tmp_path / "estado.json")
    state.data["sesion_perdida"] = []
    state.save()
    monkeypatch.setattr(cli, "cmd_postular", lambda _args: 0)
    state = State(tmp_path / "estado.json")
    state.pause(24, "LinkedIn: verificacion", kind="cuenta")
    state.save()
    cli.cmd_diario(None)
    assert "Postulación en pausa: LinkedIn: verificacion" in notices[-1]


def test_two_rounds_never_overlap(data_dir, monkeypatch, capsys):
    import fcntl

    tmp_path, _ = data_dir
    monkeypatch.setattr(cli, "cmd_buscar", lambda _args: pytest.fail("no debía correr"))
    with open(tmp_path / "vuelta.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cli.cmd_diario(None) == 0
    assert "Ya hay una vuelta" in capsys.readouterr().out
