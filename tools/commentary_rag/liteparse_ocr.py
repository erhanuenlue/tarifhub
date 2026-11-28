"""LiteParse with OCRia-nano-1: an opt-in, local OCR diagnostic beside the commentary pilot.

The pilot never imports this module and it changes nothing. It parses one PDF (a file, or a
commentary edition read from a manifest and checked against its SHA-256) with LiteParse and prints
JSON: every text item and layout block with its text, bounding box (PDF points, top-left origin,
``[x0, top, x1, bottom]``) and 1-based source page; the backend the parser reports it resolved;
the liteparse version; and, for OCRia-nano-1, the model name, version and the SHA-256 of every file
in the model package directory the library resolved.

liteparse is not a dependency of this repository. Run the tool in an ephemeral environment, from a
checkout that holds the git-ignored BAG PDFs (or name that checkout with ``--root``):

    uv run --no-project --with liteparse==2.21.4 python tools/commentary_rag/liteparse_ocr.py pull
    uv run --no-project --with liteparse==2.21.4 python tools/commentary_rag/liteparse_ocr.py \\
        parse --edition 2021-07-01 --pages 3,4 --ocr-backend ocria-nano

The backend is always chosen: ``--ocr-backend ocria-nano`` (LiteParse's OCRia-nano-1 models) or
``--ocr-backend none`` (native PDF text, OCR off). There is no default and no other engine: a
parser that resolves another backend is refused before it parses, and a missing or incomplete model
package stops the run before a parser exists. ``pull`` is the only command that downloads: it
installs ocria-nano 1.0.0 through liteparse, which checks every file against the SHA-256 pinned in
its release, into ``$LITEPARSE_MODEL_DIR/ocria-nano`` (default ``~/.cache/liteparse/models``), and
it sends no Hugging Face token. The weights have their own licence (OCRia-nano-1 Model License, a
modified OpenRAIL-M): see docs/agents/dev-tooling.md, and keep their output out of the corpus.

Exit codes: 0 done, 1 refused (input, model, backend or page attribution), 2 without liteparse or
on a usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from importlib import metadata
from pathlib import Path

try:
    from liteparse import LiteParse, ParseError, models
except ImportError:  # deliberately absent from every environment of the pilot
    LiteParse = ParseError = models = None

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
COMMENTARY_KIND = "commentary_pdf"
PIN = "2.21.4"  # the liteparse release this tool was checked against
MODEL = "ocria-nano"
MODEL_VERSION = "1.0.0"  # the package liteparse 2.21.4 installs and pins file by file
BACKENDS = (MODEL, "none")
RUN = f"uv run --no-project --with liteparse=={PIN} python tools/commentary_rag/liteparse_ocr.py"
REFUSAL = (
    "liteparse_ocr needs liteparse, which no environment of this repository installs (by design)."
    f" Run it in an ephemeral environment instead:\n  {RUN} parse --edition 2021-07-01 --pages 3,4"
    " --ocr-backend ocria-nano"
)
# The parts of the parser's resolved configuration the output reports.
REPORTED = (
    "ocr_enabled",
    "ocr_backend",
    "dpi",
    "table_model",
    "ocr_failure_fatal",
    "target_pages",
)


class Refused(RuntimeError):
    """The run cannot go ahead: bad input, a missing model, or a parser that disagrees."""


def page_list(text: str) -> list[int]:
    """``--pages``: comma-separated 1-based page numbers, returned sorted and once each."""

    try:
        pages = {int(part) for part in text.split(",") if part.strip()}
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"not a list of page numbers: {text!r}"
        ) from exc
    if not pages or min(pages) < 1:
        raise argparse.ArgumentTypeError(f"pages are numbered from 1: {text!r}")
    return sorted(pages)


def liteparse_version() -> str:
    """The version of the installed liteparse distribution."""

    return metadata.version("liteparse")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise Refused(
            f"{path}: {exc.strerror} (the BAG PDFs are git-ignored; --root names the"
            " checkout that holds them)"
        ) from exc


def documents(data: dict) -> list[dict]:
    """A manifest's commentary PDFs, from ``sources[]`` or from ``editions[].documents[]``."""

    if "sources" in data:
        return [
            {"path": s["path"], "sha256": s["sha256"], "editions": s["effective_dates"]}
            for s in data["sources"]
        ]
    return [
        {"path": d["path"], "sha256": d["sha256"], "editions": [e["effective_date"]]}
        for e in data.get("editions", [])
        for d in e["documents"]
        if d["kind"] == COMMENTARY_KIND
    ]


def pdf_input(args: argparse.Namespace) -> tuple[dict, bytes]:
    """The PDF to parse, read once; an edition's bytes must match its manifest's SHA-256."""

    if args.pdf is not None:
        content = _read(args.pdf)
        return {
            "path": str(args.pdf),
            "sha256": _sha256(content),
            "edition": None,
        }, content
    manifests = args.manifest or sorted((REPO / "data" / "manifests").glob("*.json"))
    found = [
        doc
        for manifest in manifests
        for doc in documents(json.loads(manifest.read_text(encoding="utf-8")))
        if args.edition in doc["editions"]
    ]
    if len(found) != 1:
        names = ", ".join(manifest.name for manifest in manifests)
        raise Refused(
            f"edition {args.edition}: {len(found)} commentary PDFs in {names},"
            " expected one"
        )
    entry = found[0]
    content = _read(args.root / entry["path"])
    digest = _sha256(content)
    if digest != entry["sha256"]:
        raise Refused(
            f"{entry['path']}: SHA-256 {digest}, the manifest pins {entry['sha256']}"
        )
    return {"path": entry["path"], "sha256": digest, "edition": args.edition}, content


def installed_model() -> dict:
    """The ocria-nano package the library resolved, with the SHA-256 of every file in it."""

    found = [entry for entry in models.list() if entry.name == MODEL]
    if not found:
        home = os.environ.get("LITEPARSE_MODEL_DIR") or "~/.cache/liteparse/models"
        raise Refused(
            f"{MODEL} is not installed (model directory {home}, set by"
            f" LITEPARSE_MODEL_DIR); install it once with: {RUN} pull."
            " No fallback: no other OCR engine runs instead"
        )
    entry = found[0]
    if not entry.complete:
        raise Refused(f"{MODEL} in {entry.path} is incomplete; run {RUN} pull again")
    folder = Path(entry.path)
    files = sorted(
        (path for path in folder.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(folder).as_posix(),
    )
    return {
        "name": entry.name,
        "version": entry.version,
        "path": str(folder),
        "complete": entry.complete,
        # when set, liteparse loads ONNX Runtime from here instead of runtime/
        "ort_dylib_path": os.environ.get("ORT_DYLIB_PATH"),
        "files": [
            {
                "file": path.relative_to(folder).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path.read_bytes()),
            }
            for path in files
        ],
    }


def options(backend: str, pages: list[int] | None) -> dict:
    """The LiteParse settings for one backend: always explicit, never the library's default."""

    chosen = {
        "output_format": "json",
        "extract_blocks": True,
        "extract_text_metadata": True,
        "quiet": True,
    }
    if pages:
        chosen["target_pages"] = ",".join(map(str, pages))
    if backend == MODEL:
        return {
            **chosen,
            "ocr_enabled": True,
            "ocr_backend": MODEL,
            "ocr_failure_fatal": True,
        }
    # OCR off. The backend setting is inert then, but naming one keeps an installed ocria-nano
    # package from becoming the resolved backend, which would bring its table model along.
    return {**chosen, "ocr_enabled": False, "ocr_backend": "tesseract"}


def _box(x: float, y: float, width: float, height: float) -> list[float]:
    return [x, y, x + width, y + height]


def page_record(page: object) -> dict:
    """One parsed page: its text items and blocks, each carrying the page's source number."""

    number = page.page_num
    items = [
        {
            "page": number,
            "text": item.text,
            "bbox": _box(item.x, item.y, item.width, item.height),
            "confidence": item.confidence,  # None for native PDF text; OCR output carries one
            "font": {
                "name": item.font_name,
                "size": item.font_size,
                "height": item.font_height,
                "weight": item.font_weight,
            },
        }
        for item in page.text_items
    ]
    blocks = [
        {
            "page": number,
            "kind": block.kind,
            "level": block.level,
            "bold": block.bold,
            "text": block.text,
            "bbox": None
            if block.bbox is None
            else _box(block.bbox.x, block.bbox.y, block.bbox.width, block.bbox.height),
            # indices into this page's text_items
            "text_items": list(block.text_item_indices),
        }
        for block in page.blocks or []
    ]
    return {
        "page": number,
        "page_label": page.page_label,
        "width": page.width,
        "height": page.height,
        "ocr_items": sum(i["confidence"] is not None for i in items),
        "text_items": items,
        "blocks": blocks,
    }


def resolved_config(parser: object) -> object:
    """The parser's resolved settings, as liteparse itself reports them.

    ``LiteParse.get_config()`` fails in liteparse 2.21.4 (AttributeError: its native config has no
    ``keep_clipped_text``), so this reads the native config object that get_config() reads; it
    exposes every value the output reports, among them the resolved ``ocr_backend``.
    """

    return parser._native.config


def parse(args: argparse.Namespace) -> dict:
    """Parse the requested pages with the requested backend, or refuse."""

    source, content = pdf_input(args)
    model = installed_model() if args.ocr_backend == MODEL else None
    parser = LiteParse(**options(args.ocr_backend, args.pages))
    config = resolved_config(parser)
    backend = config.ocr_backend if config.ocr_enabled else "none"
    if backend != args.ocr_backend:
        raise Refused(
            f"--ocr-backend {args.ocr_backend} was requested and liteparse resolved"
            f" {backend}: no fallback, nothing was parsed"
        )
    try:
        result = parser.parse(content)
    except ParseError as exc:
        raise Refused(f"liteparse could not parse {source['path']}: {exc}") from exc
    numbers = sorted(page.page_num for page in result.pages)
    expected = args.pages or list(range(1, result.total_pages + 1))
    if numbers != expected:
        raise Refused(
            f"liteparse returned pages {numbers} for pages {expected}: the text cannot"
            " be attributed to its source page"
        )
    return {
        "tool": "liteparse_ocr",
        "liteparse_version": liteparse_version(),
        "requested_backend": args.ocr_backend,
        "backend": backend,
        "library_config": {key: getattr(config, key) for key in REPORTED},
        "model": model,
        "source": {**source, "total_pages": result.total_pages},
        "pages": [page_record(page) for page in result.pages],
    }


def pull() -> dict:
    """Install ocria-nano through liteparse's checked pull, the only command that downloads.

    The model repository is public. liteparse would send HF_TOKEN, or the token stored under
    HF_HOME, so the pull runs without the first and with the second naming an empty directory.
    """

    saved = {key: os.environ.pop(key, None) for key in ("HF_TOKEN", "HF_HOME")}
    try:
        with tempfile.TemporaryDirectory() as empty:
            os.environ["HF_HOME"] = empty
            where = models.pull(f"{MODEL}@{MODEL_VERSION}")
    except RuntimeError as exc:
        raise Refused(f"the pull failed: {exc}") from exc
    finally:
        os.environ.pop("HF_HOME", None)
        os.environ.update(
            {key: value for key, value in saved.items() if value is not None}
        )
    print(f"installed {MODEL}@{MODEL_VERSION} into {where}", file=sys.stderr)
    return {
        "tool": "liteparse_ocr",
        "liteparse_version": liteparse_version(),
        "model": installed_model(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "pull", help=f"install {MODEL} {MODEL_VERSION} (the only download)"
    )
    parse_cmd = commands.add_parser(
        "parse", help="parse one PDF with the chosen backend"
    )
    source = parse_cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path, help="a PDF file")
    source.add_argument(
        "--edition", help="a commentary's effective date, e.g. 2021-07-01"
    )
    parse_cmd.add_argument(
        "--pages",
        type=page_list,
        default=None,
        help="1-based source pages, e.g. 3,4 (default: all)",
    )
    parse_cmd.add_argument(
        "--ocr-backend",
        required=True,
        choices=BACKENDS,
        help="ocria-nano, or none for the native PDF text",
    )
    parse_cmd.add_argument(
        "--root", type=Path, default=REPO, help="checkout holding data/raw"
    )
    parse_cmd.add_argument(
        "--manifest",
        type=Path,
        action="append",
        help="manifest for --edition (repeatable; default data/manifests/*)",
    )
    parse_cmd.add_argument(
        "--out", type=Path, default=None, help="write the JSON to this file"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command: 0 done, 1 refused, 2 without liteparse."""

    args = _parser().parse_args(argv)
    if LiteParse is None or models is None:
        print(REFUSAL, file=sys.stderr)
        return 2
    try:
        report = pull() if args.command == "pull" else parse(args)
    except Refused as exc:
        print(f"liteparse_ocr refused: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if getattr(args, "out", None) is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
