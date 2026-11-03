"""Command line: python -m newsroom <command>."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import ROOT
from .config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="newsroom", description="The 403 Times")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_render_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--fixtures", action="store_true",
                       help="render the sample editions in tests/fixtures instead of data/")
        p.add_argument("--front", metavar="EDITION_ID",
                       help="edition to use as the front page (default: the latest)")
        p.add_argument("--out", type=Path, default=ROOT / "_site", help="output directory")

    add_render_args(sub.add_parser("render", help="render the static site"))
    serve_p = sub.add_parser("serve", help="render, then preview locally")
    add_render_args(serve_p)
    serve_p.add_argument("--port", type=int, default=8403)

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.command in ("render", "serve"):
        from .render import build

        data_dir = ROOT / "tests" / "fixtures" if args.fixtures else ROOT / "data"
        pages = build(cfg, data_dir=data_dir, out_dir=args.out,
                      front_edition=args.front, preview=args.fixtures)
        print(f"Rendered {pages} pages to {args.out}")
        if args.command == "serve":
            from .serve import serve

            serve(args.out, cfg["site"]["base_path"], args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
