"""The local Botroom lab: labels, saved trials, and request checks. No model calls."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from newsroom import ROOT


def load_lab():
    path = ROOT / "scripts" / "forum_lab.py"
    spec = importlib.util.spec_from_file_location("forum_lab", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lab = load_lab()


def test_label_slug_keeps_a_short_safe_name():
    assert lab.label_slug("Grounded reply!") == "grounded-reply"
    assert lab.label_slug("   ") == "try"
    assert len(lab.label_slug("a" * 80)) <= 40


def test_parse_job_keeps_a_rewritten_base_prompt():
    job = lab.parse_job({"title": "A thread", "brief": "The brief", "prompt": "Talk plainly."})
    assert job["prompt"] == "Talk plainly."
    same = lab.parse_job({"title": "A thread", "brief": "The brief", "prompt": lab.PROMPT.read_text(encoding="utf-8")})
    assert same["prompt"] == ""
    with pytest.raises(lab.LabError):
        lab.parse_job({"title": "A thread", "brief": "The brief", "prompt": "   "})


def test_system_prompt_uses_the_given_rules():
    news = lab.Day(date=lab.date(2026, 11, 13), around=["Grandma_Kernel"])
    text = lab.system_prompt("", None, news, rules="House rule.")
    assert text.startswith("House rule.")
    assert "Who's around today" in text


def test_parse_job_rejects_an_unknown_model():
    with pytest.raises(lab.LabError):
        lab.parse_job({"title": "A thread", "brief": "The brief", "model": "opus"})


def test_runs_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "lab_root", lambda: tmp_path)
    run = tmp_path / "20261113-180627"
    run.mkdir()
    (run / "grounded.json").write_text(json.dumps({
        "variant": "grounded", "extra": True, "comments": [{"id": "c1", "handle": "A", "text": "Hi"}],
    }), encoding="utf-8")
    (run / "fixture.json").write_text(json.dumps({"title": "T", "brief": "B"}), encoding="utf-8")

    assert lab.list_runs() == [{"id": "20261113-180627", "variants": ["grounded"]}]
    loaded = lab.load_run("20261113-180627")
    assert loaded["fixture"]["title"] == "T"
    assert "Name the specific title" in loaded["variants"][0]["extra_text"]
    with pytest.raises(lab.LabError):
        lab.load_run("../data")


def test_same_fixture_treats_a_missing_file_as_the_edition():
    edition = {"title": "T", "brief": "B"}
    assert lab._same_fixture(None, "T", "B", edition)
    assert not lab._same_fixture(None, "T", "Other", edition)
    assert not lab._same_fixture({"title": "T", "brief": "Other"}, "T", "B", edition)
