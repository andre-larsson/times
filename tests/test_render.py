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
