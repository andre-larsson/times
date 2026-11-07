"""Smoke tests: render the sample editions and check the output is a working site."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from newsroom import ROOT
from newsroom.config import load_config
from newsroom.render import build, quote_slot

FIXTURES = ROOT / "tests" / "fixtures"
LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def site(tmp_path_factory, cfg) -> Path:
    out = tmp_path_factory.mktemp("site")
    build(cfg, data_dir=FIXTURES, out_dir=out, preview=True)
    return out


def test_expected_pages_exist(site):
    for rel in [
        "index.html", "ai/index.html", "tech/index.html", "gaming/index.html", "deals/index.html",
        "archive/index.html", "archive/2026-11-02/index.html", "archive/2026-11-03/index.html",
        "2026/11/03/kestrel-2-open-model-catches-big-labs/index.html",
        "2026/11/03/build-the-pc-this-winter/index.html", "opinion/index.html",
        "quiz/index.html", "quiz/2026-11-03/index.html", "static/quiz.js", "static/weather.js",
        "404.html", "feed.xml", "static/style.css", "static/favicon.svg",
    ]:
        assert (site / rel).is_file(), rel


def test_internal_links_resolve(site, cfg):
    base = cfg["site"]["base_path"]
    broken = []
    for page in site.rglob("*.html"):
        for link in LINK_RE.findall(page.read_text(encoding="utf-8")):
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            assert link.startswith(base), f"{page.relative_to(site)}: {link} is not under {base}"
            target = site / link[len(base):].split("?")[0].split("#")[0]
            if not (target.is_file() or (target / "index.html").is_file()):
                broken.append(f"{page.relative_to(site)} -> {link}")
    assert not broken, "\n".join(broken)


def test_feed_is_valid_atom(site):
    root = ET.parse(site / "feed.xml").getroot()
    entries = root.findall("{http://www.w3.org/2005/Atom}entry")
    assert entries, "feed has no entries"


def test_front_page_content(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "Kestrel&#39;s free model catches the big labs at coding" in html
    assert "Top on Hacker News" in html
    assert "Deal of the day" in html
    assert 'name="robots" content="noindex' in html
    assert "Design preview" in html  # fixtures are clearly marked


def test_weather_box_is_live_on_todays_front_page_only(site, cfg):
    w = cfg["weather"]
    html = (site / "index.html").read_text(encoding="utf-8")
    assert f'data-place="{w["place"]}" data-lat="{w["latitude"]}" data-lon="{w["longitude"]}"' in html
    assert "static/weather.js" in html and ">Weather data by Open-Meteo.com</a>" in html   # CC BY 4.0 credit
    archived = (site / "archive" / "2026-11-03" / "index.html").read_text(encoding="utf-8")
    assert "data-weather" not in archived and "static/weather.js" not in archived


def test_quiz_page(site):
    html = (site / "quiz" / "2026-11-03" / "index.html").read_text(encoding="utf-8")
    assert html.count('class="quiz-q ') == 5 and html.count("quiz-opt--right") == 5
    assert html.count('type="radio" name="q1"') == 4 and "static/quiz.js" in html
    assert 'href="/times/2026/11/03/kestrel-2-open-model-catches-big-labs/"' in html   # our article page
    assert 'href="https://example.com/pixel-courier/showcase"' in html                  # gaming news: the source
    assert "Not quite. Right answer: 71.4%<" in html
    assert 'data-quiz="2026-11-03"' in html and html.count("data-quiz-advance") == 5     # one question at a time
    assert "data-quiz-start" in html and html.count("data-quiz-goto=") == 5                  # start, result recap
    front = (site / "index.html").read_text(encoding="utf-8")
    assert 'aria-label="Quiz"' in front and "The Tuesday quiz" in front and ">Quiz</a>" in front   # rail card, nav
    index = (site / "quiz" / "index.html").read_text(encoding="utf-8")
    for page in (front, index):                  # cards get "Completed" from the result saved in the browser
        assert 'data-quiz-card="2026-11-03"' in page and "data-quiz-done hidden" in page and "static/quiz.js" in page
    assert "The Tuesday quiz" in (site / "archive" / "index.html").read_text(encoding="utf-8")
    assert "/times/quiz/2026-11-03/" in (site / "feed.xml").read_text(encoding="utf-8")


def test_links_edition_renders(tmp_path, cfg):
    build(cfg, data_dir=FIXTURES, out_dir=tmp_path / "out", front_edition="2026-11-02")
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "Links edition." in html
    assert "Linux 7.1 released with a new scheduler" in html
    assert "Design preview" not in html  # only shown when preview=True


def test_refuses_to_wipe_project(cfg):
    with pytest.raises(SystemExit):
        build(cfg, data_dir=FIXTURES, out_dir=ROOT)


def test_opinion_column(site):
    front = (site / "index.html").read_text(encoding="utf-8")
    assert "Build the PC this winter, not next year" in front              # on the front page for a week
    assert '/times/opinion/"' in front                                     # and in the nav
    page = (site / "2026/11/03/build-the-pc-this-winter/index.html").read_text(encoding="utf-8")
    assert "Column by Claude (AI)" in page and 'class="pull-quote"' in page
    assert 'href="/times/2026/11/03/arcwave-r9-review-roundup/"' in page   # reporting links to our article
    assert 'href="https://example.com/circuit-weekly/budget-gpus"' in page  # briefs link to the source
    assert "build-the-pc-this-winter" in (site / "feed.xml").read_text(encoding="utf-8")


def test_column_not_on_earlier_fronts(tmp_path, cfg):
    build(cfg, data_dir=FIXTURES, out_dir=tmp_path / "out", front_edition="2026-11-02")
    assert "Build the PC this winter" not in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")


def test_pull_quote_is_not_next_to_its_paragraph():
    paras = ["a", "b QUOTE", "c", "d", "e"]
    assert quote_slot(paras, "QUOTE") == 3                     # not right after (or before) paragraph 2
    assert quote_slot(["x QUOTE", "b", "c", "d"], "QUOTE") == 2
    assert quote_slot(paras[:3], "QUOTE") == 0                 # too short for a pull quote
    assert quote_slot(paras, "") == 0


def test_deals_use_ratings_not_imperatives(site):
    html = (site / "deals" / "index.html").read_text(encoding="utf-8")
    for label in ("Strong Buy", "Hold", "Avoid"):
        assert f"{label}</span>" in html, label
    assert "verdict--strong_buy" in html and "Buy it" not in html
    assert '<span class="chip chip--pick">Hidden gem</span>' in html            # where a deal came from
    assert '<span class="chip chip--pick">Horror</span>' in html


def test_gaming_shows_critic_averages_and_outlet_scores(site):
    html = (site / "gaming" / "index.html").read_text(encoding="utf-8")
    assert ('<a class="critic critic--positive" href="https://example.com/opencritic/hollow-lantern" '
            'title="Average of 42 critic reviews"><b class="critic-score">87</b> OpenCritic</a>') in html
    assert ('<span class="critic critic--negative" title="Average of 12 critic reviews">'
            '<b class="critic-score">48</b> Metascore</span>') in html                  # no link from ITAD
    assert 'href="https://example.com/metacritic/hollow-lantern"' not in html          # direct link instead
    assert 'href="https://example.com/metacritic/ashen-rails"' in html                 # search link kept
    assert '<span class="score"><span>9<small class="score-scale">/10</small></span></span>' in html
    assert '<span class="score"><span>82</span></span>' in html
    assert '<span class="score score--word">Recommended</span>' in html


def test_search_page_and_index(site, cfg):
    import json

    from newsroom.search import build_index

    html = (site / "search" / "index.html").read_text(encoding="utf-8")
    assert 'data-index="/times/search/index.json?v=' in html and "static/search.js?v=" in html
    assert 'value="opinion"' in html                                   # a filter per section, Opinion included
    rows = json.loads((site / "search" / "index.json").read_text(encoding="utf-8"))["items"]
    assert [r["t"] for r in rows] == sorted((r["t"] for r in rows), reverse=True)    # newest first
    kinds = {r["n"] for r in rows}
    assert {"", "Brief", "Column", "News", "Review", "Link"} <= kinds, kinds
    base = cfg["site"]["base_path"]
    for r in rows:
        assert r["h"] and r["s"] and r["t"], r
        if not r["u"].startswith("http"):                              # our pages must exist
            target = site / r["u"][len(base):]
            assert r["u"].startswith(base) and (target / "index.html").is_file(), r["u"]
    archive = (site / "archive" / "index.html").read_text(encoding="utf-8")
    assert 'action="/times/search/"' in archive

    same = {"headline": "Same story", "summary": "", "url": "https://example.com/same"}
    eds = [{"edition_id": "2026-11-01", "gaming": {"news": [same]}},
           {"edition_id": "2026-11-02", "gaming": {"news": [same]}}]
    assert [r["t"] for r in build_index(eds, lambda s: "#")] == ["2026-11-01"]   # first seen, listed once
