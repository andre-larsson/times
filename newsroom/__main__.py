"""Command line: python -m newsroom <command>."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from . import ROOT
from .config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="newsroom", description="The 403 Times")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_data_dir(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", type=Path, default=ROOT / "data",
                       help="where editions live (default: data/)")

    def add_render_args(p: argparse.ArgumentParser) -> None:
        add_data_dir(p)
        p.add_argument("--fixtures", action="store_true",
                       help="render the sample editions in tests/fixtures instead of --data-dir")
        p.add_argument("--front", metavar="EDITION_ID",
                       help="edition to use as the front page (default: the latest)")
        p.add_argument("--out", type=Path, default=ROOT / "_site", help="output directory")

    add_render_args(sub.add_parser("render", help="render the static site"))
    serve_p = sub.add_parser("serve", help="render, then preview locally")
    add_render_args(serve_p)
    serve_p.add_argument("--port", type=int, default=8403)

    gen_p = sub.add_parser("generate", help="fetch sources and write today's edition if one is due")
    add_data_dir(gen_p)
    gen_p.add_argument("--mode", default="auto", choices=("auto", "full", "reduced", "links", "skip"),
                       help="auto = follow the schedule and the pre-run check; others force a run now")
    gen_p.add_argument("--now", type=dt.datetime.fromisoformat, help="pretend it is this time (testing)")
    gen_p.add_argument("--dump", type=Path, help="also write everything fetched to this JSON file")

    src_p = sub.add_parser("sources", help="fetch every source once and report what came back")
    src_p.add_argument("--dump", type=Path, help="write everything fetched to this JSON file")

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.command in ("render", "serve"):
        from .render import build

        data_dir = ROOT / "tests" / "fixtures" if args.fixtures else args.data_dir
        pages = build(cfg, data_dir=data_dir, out_dir=args.out,
                      front_edition=args.front, preview=args.fixtures)
        print(f"Rendered {pages} pages to {args.out}")
        if args.command == "serve":
            from .serve import serve

            serve(args.out, cfg["site"]["base_path"], args.port)
        return 0

    if args.command == "generate":
        from .generate import dump_harvest, generate, report, write_github_outputs

        now = args.now.astimezone(dt.timezone.utc) if args.now else None
        result = generate(cfg, args.data_dir, args.mode, now=now)
        print(report(result))
        if result.path:
            print(f"\nWrote {result.path}")
        if args.dump and result.harvest:
            dump_harvest(result.harvest, args.dump)
        write_github_outputs(result)
        return 0

    if args.command == "sources":
        import os

        from .generate import Result, dump_harvest, report
        from .http import Client
        from .sources import fetch_all

        with Client() as client:
            harvest = fetch_all(cfg, client, itad_key=os.environ.get("ITAD_API_KEY") or None)
        print(report(Result(False, "check", "sources only", harvest=harvest)))
        if args.dump:
            dump_harvest(harvest, args.dump)
        failed = [s for s in harvest.status if not s.ok and not s.skipped]
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
