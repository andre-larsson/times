"""Discussion material from the rest of the newspaper, including older still-current features."""

from __future__ import annotations

import json
from datetime import date
from typing import Any


def feature_threads(edition: dict[str, Any], editions: list[dict[str, Any]],
                    used: set[str]) -> list[dict[str, Any]]:
    today = date.fromisoformat(edition["edition_id"][:10])
    recent = sorted([e for e in editions if e["edition_id"] < edition["edition_id"]] + [edition],
                    key=lambda e: e["edition_id"], reverse=True)
    out = []
    for kind in ("opinion", "quiz", "screen", "arcade"):
        for ed in recent:
            if (today - date.fromisoformat(ed["edition_id"][:10])).days > 7:
                break
            content = (ed.get("screen") or {}).get("picks") if kind == "screen" else ed.get(kind)
            if not content:
                continue
            key = f"{kind}:{ed['edition_id']}"
            if key in used:
                break
            title = content.get("headline") or content.get("title") or f"{kind.title()} · {ed['edition_id']}"
            if kind == "opinion":
                material = {k: content.get(k) for k in ("headline", "dek", "body")}
                path = f"{ed['edition_id'][:4]}/{ed['edition_id'][5:7]}/{ed['edition_id'][8:10]}/{content['slug']}/"
            elif kind == "quiz":
                material = {"questions": [{k: q.get(k) for k in ("question", "options", "answer", "explanation")}
                                          for q in content.get("questions", [])]}
                path = f"quiz/{ed['edition_id']}/"
                # A neutral title/description is safe to show in board lists and the shared prompt.
                title = f"Quiz discussion · {ed['edition_id']}"
            elif kind == "arcade":
                material = {
                    "title": content.get("title", ""),
                    "dek": content.get("dek", ""),
                    "genre": content.get("genre_label") or content.get("genre", ""),
                    "controls_layout": content.get("controls_layout", ""),
                    "news_tie": content.get("news_tie", ""),
                    "story": (content.get("story") or {}).get("headline", ""),
                }
                path = f"arcade/{ed['edition_id']}/"
            else:
                material = {"headline": title, "picks": [_title(t) for t in content.get("titles", [])]}
                path = "screen/"
            out.append(dict(kind=kind, section=kind, board=kind, title=title, slug=f"{kind}-{ed['edition_id']}",
                            content_key=key, content_path=path, label="Spoilers" if kind == "quiz" else kind.title(),
                            dek="Answers and discussion. Take the quiz before opening this thread." if kind == "quiz"
                            else content.get("dek", ""), pop=2, spoiler=kind == "quiz",
                            brief=json.dumps(material, ensure_ascii=False)))
            break
    # Between weekly picks, a small selection from today's actual Screen lists can start a conversation.
    if not any(t["kind"] == "screen" for t in out):
        screen = edition.get("screen") or {}
        titles = [t for group in screen.get("new", []) for t in group.get("titles", [])] + screen.get("classics", [])
        fresh = [t for t in titles if f"screen-title:{t.get('key')}" not in used]
        if fresh:
            t = fresh[0]
            out.append(dict(kind="screen", section="screen", board="screen", title=f"Screen: {t['title']}",
                            slug=f"screen-{t.get('key', 'watch').replace(':', '-')}",
                            content_key=f"screen-title:{t.get('key')}", content_path="screen/", label="What to watch",
                            dek=t.get("overview", ""), pop=1.5, brief=json.dumps(_title(t), ensure_ascii=False)))
    return out


def _title(t: dict[str, Any]) -> dict[str, Any]:
    return {k: t[k] for k in ("title", "kind", "year", "overview", "genres", "rating", "on", "reason") if k in t}
