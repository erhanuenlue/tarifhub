"""LiteParse with OCRia-nano-1: an opt-in, local OCR diagnostic beside the commentary pilot.

The pilot never imports this module and it changes nothing. It parses one PDF (a file, or a
commentary edition read from a manifest and checked against its SHA-256) with LiteParse and prints
JSON: every text item and layout block (table cells, code and grid lines included) with its text,
bounding box (PDF points, top-left origin, ``[x0, top, x1, bottom]``) and 1-based source page; the
backend the parser reports it resolved; the liteparse version; and, for OCRia-nano-1, the model
name, version and every file of the package with its SHA-256.

liteparse is not a dependency of this repository. Run the tool in an ephemeral environment, from a
checkout that holds the git-ignored BAG PDFs (or name that checkout with ``--root``):

    uv run --no-project --with liteparse==2.21.4 python tools/commentary_rag/liteparse_ocr.py pull
    uv run --no-project --with liteparse==2.21.4 python tools/commentary_rag/liteparse_ocr.py \\
        parse --edition 2021-07-01 --pages 3,4 --ocr-backend ocria-nano

``parse`` never downloads a model, but ``uv run --with`` fetches liteparse itself when uv's cache
lacks it. ``uv --offline`` stops only uv's own fetches, not the parser process (liteparse turns
ONNX Runtime's telemetry off only when ``ORT_DISABLE_TELEMETRY`` is unset; an inherited value is
kept), so a parse without network is the one run, with a warm cache, under the network-denying
sandbox: ``sandbox-exec -p "(version 1)(allow default)(deny network*)" uv run --offline
--no-project --with liteparse==2.21.4 ...``.

The backend is always chosen: ``--ocr-backend ocria-nano`` (LiteParse's OCRia-nano-1 models) or
``--ocr-backend none`` (native PDF text, OCR off). There is no default and no other engine: a
parser that resolves another backend is refused before it parses. Before a parser exists, the
model package must be ocria-nano 1.0.0 with exactly the sixteen files pinned below, each matching
its size and SHA-256 (verified for macOS arm64 only; other platforms are refused), and neither
``ORT_DYLIB_PATH`` nor a dynamic-loader override (``DYLD_*``, ``LD_LIBRARY_PATH``, ``LD_PRELOAD``)
may be set, not even empty: the pins cannot vouch for another ONNX Runtime. liteparse
reports an OCR failure on a page only on native stderr and returns the page anyway, so the parse
runs with file descriptor 2 captured: any ``[ocr]`` failure line refuses the whole run and no
report is written. A page with no OCR text in a written report therefore had no OCR failure.

``pull`` is the only command that downloads. It first refuses what it could not verify afterwards
(another platform, a runtime or loader override), then installs ocria-nano 1.0.0 through liteparse,
which checks the model files and the ONNX Runtime against the SHA-256 pinned in its release while
it downloads, into ``$LITEPARSE_MODEL_DIR/ocria-nano`` (default ``~/.cache/liteparse/models``, on
Windows ``%LOCALAPPDATA%\\liteparse\\models``; an empty value means the current directory), and
sends no Hugging Face token. This tool then checks all sixteen pins, among them ``LICENSE``, which
liteparse fetches without a check, and ``manifest.json``, which the pull writes.

An edition's PDF must lie inside ``--root`` once links are resolved and must not itself be a link.
``--out`` must name a new file in an existing folder (an existing file is never replaced). If that
folder lies in a Git working tree (this checkout, ``--root``, or any other worktree or clone, as
``git rev-parse --show-toplevel`` finds it), the file may only go under that tree's git-ignored
``tools/commentary_rag/local/``, which must be a real folder; when git cannot tell, the run is
refused. Without ``--out`` the JSON goes to stdout. The weights have their own licence (OCRia-nano-1 Model License,
a modified OpenRAIL-M): see docs/agents/dev-tooling.md, and keep their output out of the corpus.

Exit codes: 0 done, 1 refused (input, output, model, backend, OCR or page attribution), 2 without
liteparse or on a usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
import platform
import subprocess
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
LOCAL = (
    "tools",
    "commentary_rag",
    "local",
)  # git-ignored: the one folder a report may go to
GIT = "git"  # asked which Git working tree, if any, holds --out
# ORT_DYLIB_PATH and the dynamic-loader variables that could make liteparse load another ONNX
# Runtime than the pinned one: present at all, even empty, they refuse the OCRia-nano path.
LOADER_OVERRIDES = (
    "ORT_DYLIB_PATH",
    "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
)
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
# ocria-nano 1.0.0 as liteparse 2.21.4 installs it on macOS arm64, file by file (bytes, SHA-256),
# checked on 2026-11-28: the model files equal liteparse's release pins and Hugging Face's files at
# revision v1.0.0, the ONNX Runtime library equals liteparse's NuGet pin, LICENSE equals Hugging
# Face's git object, and manifest.json is the one liteparse's pull writes. Other platforms get
# other files (tablenet.onnx, another ONNX Runtime build), which nobody has checked here.
PLATFORM = ("darwin", "arm64")
PACKAGE = {
    "LICENSE": (
        18383,
        "f1cee1fc810a9ba0553df347ca1238eb43efb4c9c87f590a8b17a06af6dcfd46",
    ),
    "det.meta.json": (
        17,
        "ada6b3c5de0800eb43fa81dbec714d47cd2a712a22952ef23cf38c805b27350e",
    ),
    "det.onnx": (
        347580,
        "70ea641d74c4d7d3acb734002cc1507350d8350ad44aeedc6f8ac6017dbcff7a",
    ),
    "manifest.json": (
        65,
        "60671d4fa7fae946d76bb8679c69b1377f2a6e165c66ffe8b6e25100c667346e",
    ),
    "rec_cjk.charset.json": (
        43274,
        "0e48eca81c1c0afa5a3e081fdf5fcbdc669e746e7e0a7f264e85ac76c496035b",
    ),
    "rec_cjk.onnx": (
        5077778,
        "ad7154b54a549dbfead48dd49142bcc76ee168cb0cd874f6efacab543f0b9262",
    ),
    "rec_latin.charset.json": (
        4933,
        "d386eea5691a4f3d9e40f48a3979cf859caf626c3ec43214c7911a713e1f4ed0",
    ),
    "rec_latin.onnx": (
        943530,
        "7ac8f6815b4b127f244c14f86c51f65224c82e022c1ee71f867f2be955be4da4",
    ),
    "rec_rtl.charset.json": (
        1876,
        "8ad9b8f6c1bdc17b42a2351948e84a73c487f5bed7f783bc5e8474efad126a80",
    ),
    "rec_rtl.meta.json": (
        20,
        "31fd2893cc4d48ec50b4b21a1f113f527ae9a4ac1b3ea395b0cc5969f56d46b5",
    ),
    "rec_rtl.onnx": (
        2842451,
        "9ccee36bb07b81ef310c6b50e707adabe8c6b92caea61105213686ea8977f4cf",
    ),
    "rec_world.charset.json": (
        11602,
        "ebfd39142cec3f267eda2b81b42966ac9b0f73841a52285770f4db40a016d689",
    ),
    "rec_world.onnx": (
        3913987,
        "c57d01a945d741886d356bdedc636f0572d0810c6a7c2f26dbb9ce0466b92220",
    ),
    "router.onnx": (
        159029,
        "daccb2e3ce3891b7cb95037ada3861e05fd288d7678d2a1e662d9483e04dd361",
    ),
    "runtime/libonnxruntime.dylib": (
        44830288,
        "2685dc296147c47b0dbd8e0615547b12fc0c445d158d1f374cbd0705d9626fdc",
    ),
    "tablenet.bin": (
        17084482,
        "27b5f3ff2d6842d397a21954026b1e6411e8b35085b0b32c616e67e33852d1b4",
    ),
}
# What the output reports of the parser's resolved configuration (output key: config field).
# liteparse reports only an explicit table model; the one ocria-nano brings is not shown there.
REPORTED = {
    "ocr_enabled": "ocr_enabled",
    "ocr_backend": "ocr_backend",
    "dpi": "dpi",
    "table_model_override": "table_model",
    "ocr_failure_fatal": "ocr_failure_fatal",
    "target_pages": "target_pages",
}


class Refused(RuntimeError):
    """The run cannot go ahead: bad input or output, the model, or a parser that disagrees."""


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


def this_platform() -> tuple[str, str]:
    """The operating system and machine, as the pins name them."""

    return sys.platform, platform.machine()


def model_home() -> str:
    """The folder liteparse searches for model packages: LITEPARSE_MODEL_DIR (set but empty, the
    current directory), else its default."""

    if "LITEPARSE_MODEL_DIR" in os.environ:
        return os.environ["LITEPARSE_MODEL_DIR"] or (
            f"{os.getcwd()}, the current directory (LITEPARSE_MODEL_DIR is set but empty)"
        )
    if this_platform()[0] == "win32":
        base = os.environ.get("LOCALAPPDATA", "%LOCALAPPDATA%")
        return ntpath.join(base, "liteparse", "models")
    return "~/.cache/liteparse/models"


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


def _inside(target: Path, folder: Path) -> bool:
    """Whether the resolved ``target`` lies in ``folder``, however either is spelled (a link,
    another letter case)."""

    if target.is_relative_to(folder.resolve()):
        return True
    return folder.is_dir() and any(
        candidate.exists() and os.path.samefile(candidate, folder)
        for candidate in (target, *target.parents)
    )


def _work_tree(folder: Path) -> Path | None:
    """The Git working tree that holds ``folder``, or None outside any; refused when git cannot
    tell (no git, a folder inside .git, a repository git declines to read)."""

    env = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    env.update(LC_ALL="C", LANGUAGE="C")  # git's own words, whatever the locale
    try:
        asked = subprocess.run(
            [GIT, "-C", str(folder), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    except OSError as exc:
        raise Refused(
            f"git cannot tell whether --out lies in a Git working tree ({exc.strerror});"
            " nothing is written"
        ) from exc
    if asked.returncode == 0:
        return Path(asked.stdout.strip())
    if "not a git repository" in asked.stderr:
        return None
    raise Refused(
        "git cannot tell whether --out lies in a Git working tree"
        f" ({asked.stderr.strip() or asked.returncode}); nothing is written"
    )


def check_output(path: Path, checkouts: list[Path]) -> None:
    """Refuse an ``--out`` that exists, or that lies in a Git working tree (this checkout,
    ``--root``, or any other worktree or clone) outside that tree's git-ignored local folder,
    before any input is read: page text must not land where Git sees it."""

    if not path.parent.is_dir():
        raise Refused("--out must name a new file in an existing folder")
    target = path.resolve()
    written = Path(os.path.abspath(path))  # as given: a link on the way is not followed
    tree = _work_tree(target.parent)
    for repo in [*checkouts, *([tree] if tree else [])]:
        local = repo.joinpath(*LOCAL)
        if not (_inside(target, repo) or _inside(written, repo)):
            continue
        if local.is_symlink():
            raise Refused(
                f"{local} is a symbolic link; write the report to the real, git-ignored"
                " folder or outside any Git working tree"
            )
        if not _inside(target, local):
            raise Refused(
                f"--out lies in {repo} outside tools/commentary_rag/local/ (git-ignored);"
                " write the report there or outside any Git working tree"
            )
    if path.exists() or path.is_symlink():
        raise Refused(f"--out {path} already exists; a report never replaces a file")


def documents(data: dict) -> list[dict]:
    """A manifest's commentary PDFs, from ``sources[]`` or from ``editions[].documents[]``; a
    manifest with neither section, or with a path no file system can take, is a ValueError."""

    if not isinstance(data, dict) or not ("sources" in data or "editions" in data):
        raise ValueError("neither a sources nor an editions section")
    if "sources" in data:
        listed = [
            (s["path"], s["sha256"], s["effective_dates"]) for s in data["sources"]
        ]
    else:
        listed = [
            (d["path"], d["sha256"], [e["effective_date"]])
            for e in data["editions"]
            for d in e["documents"]
            if d["kind"] == COMMENTARY_KIND
        ]
    if not all(
        isinstance(path, str)
        and "\x00" not in path
        and isinstance(digest, str)
        and isinstance(dates, list)
        for path, digest, dates in listed
    ):
        raise ValueError(
            "a path (an embedded NUL included), SHA-256 or list of effective dates"
            " is malformed"
        )
    return [
        {"path": path, "sha256": digest, "editions": dates}
        for path, digest, dates in listed
    ]


def _manifest_documents(manifest: Path) -> list[dict]:
    try:
        return documents(json.loads(manifest.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise Refused(
            f"{manifest}: not a readable manifest ({type(exc).__name__}: {exc})"
        ) from exc


def pdf_input(args: argparse.Namespace) -> tuple[dict, bytes]:
    """The PDF to parse, read once; an edition's file must lie inside --root, must not be a
    link, and its bytes must match the manifest's SHA-256."""

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
        for doc in _manifest_documents(manifest)
        if args.edition in doc["editions"]
    ]
    if len(found) != 1:
        names = ", ".join(manifest.name for manifest in manifests)
        raise Refused(
            f"edition {args.edition}: {len(found)} commentary PDFs in {names},"
            " expected one"
        )
    entry = found[0]
    located = args.root / entry["path"]
    try:
        linked = located.is_symlink()
        target = located.resolve()
    except (
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:  # a link loop, an unreadable folder
        raise Refused(f"{entry['path']!r}: {type(exc).__name__}: {exc}") from exc
    if linked:
        raise Refused(
            f"{entry['path']}: a symbolic link; the manifest must name the file itself"
        )
    if not target.is_relative_to(args.root.resolve()):
        raise Refused(f"{entry['path']}: resolves outside --root ({args.root})")
    content = _read(target)
    digest = _sha256(content)
    if digest != entry["sha256"]:
        raise Refused(
            f"{entry['path']}: SHA-256 {digest}, the manifest pins {entry['sha256']}"
        )
    return {"path": entry["path"], "sha256": digest, "edition": args.edition}, content


def check_runtime_environment() -> None:
    """Refuse what the asset pins cannot vouch for: another platform, or ORT_DYLIB_PATH or a
    dynamic-loader override that could make liteparse load another ONNX Runtime (set at all,
    even empty)."""

    if this_platform() != PLATFORM:
        raise Refused(
            f"the asset pins of {MODEL} {MODEL_VERSION} are verified for macOS arm64"
            f" only, not for {' '.join(this_platform())}"
        )
    present = [name for name in LOADER_OVERRIDES if name in os.environ]
    if present:
        raise Refused(
            f"{', '.join(present)} set (even an empty value counts): liteparse could load an"
            " ONNX Runtime the asset pins do not cover; unset it"
        )


def installed_model() -> dict:
    """The ocria-nano package the library resolved, refused unless it is version 1.0.0 with
    exactly the pinned files, each matching its pinned size and SHA-256."""

    found = [entry for entry in models.list() if entry.name == MODEL]
    if not found:
        raise Refused(
            f"{MODEL} is not installed in {model_home()} (LITEPARSE_MODEL_DIR, else"
            f" liteparse's default model directory); install it once with: {RUN}"
            " pull. No fallback: no other OCR engine runs instead"
        )
    entry = found[0]
    if not entry.complete:
        raise Refused(f"{MODEL} in {entry.path} is incomplete; run {RUN} pull again")
    check_runtime_environment()
    if entry.version != MODEL_VERSION:
        raise Refused(
            f"{MODEL} {entry.version} is installed; the asset pins are for"
            f" {MODEL_VERSION}"
        )
    folder = Path(entry.path)
    present = {
        path.relative_to(folder).as_posix(): path
        for path in folder.rglob("*")
        if path.is_file()
    }
    missing, extra = (
        sorted(set(PACKAGE) - set(present)),
        sorted(set(present) - set(PACKAGE)),
    )
    if missing or extra:
        raise Refused(
            f"{MODEL} in {folder} does not match its pins: missing {missing or 'none'},"
            f" not pinned {extra or 'none'}"
        )
    files = []
    for name in sorted(PACKAGE):
        data = present[name].read_bytes()
        size, digest = PACKAGE[name]
        if len(data) != size or _sha256(data) != digest:
            raise Refused(
                f"{MODEL} file {name}: {len(data)} bytes, SHA-256 {_sha256(data)};"
                f" its pin is {size} bytes, {digest}"
            )
        files.append({"file": name, "bytes": size, "sha256": digest})
    return {
        "name": entry.name,
        "version": entry.version,
        "path": str(folder),
        "complete": entry.complete,
        "assets_match_pins": True,
        "loader_overrides": "none",
        "files": files,
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


def _rect(rect: object) -> list[float] | None:
    return None if rect is None else _box(rect.x, rect.y, rect.width, rect.height)


def _cells(cells: list | None, number: int) -> list[dict] | None:
    if cells is None:
        return None
    return [
        {
            "page": number,
            "text": cell.text,
            "bbox": _rect(cell.bbox),
            "text_items": list(cell.text_item_indices),
        }
        for cell in cells
    ]


def page_record(page: object) -> dict:
    """One parsed page: its text items and blocks (every field of liteparse's LayoutBlock, table
    cells with their boxes), each carrying the page's source number."""

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
            "italic": block.italic,
            "ordered": block.ordered,
            "marker": block.marker,
            "text": block.text,
            "lines": None if block.lines is None else list(block.lines),
            "lang": block.lang,
            "header": _cells(block.header, number),
            "rows": None
            if block.rows is None
            else [_cells(row, number) for row in block.rows],
            "id": block.id,
            "format": block.format,
            "bbox": _rect(block.bbox),
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


def parse_watching_stderr(parser: object, content: bytes) -> tuple[object, list[str]]:
    """Parse ``content`` with file descriptor 2 captured, and return the result with liteparse's
    OCR failure lines.

    liteparse 2.21.4 reports a page whose OCR failed only there (``[ocr] failed for page N: ...``
    for the first, then ``[ocr] k/n page(s) failed OCR; continuing with partial results``), not to
    Python, and returns the page anyway; every ``[ocr] `` line it prints is such a failure. What
    was captured is passed on to stderr.
    """

    sys.stderr.flush()
    saved = os.dup(2)
    with tempfile.TemporaryFile() as sink:
        os.dup2(sink.fileno(), 2)
        try:
            result = parser.parse(content)
        finally:
            os.dup2(saved, 2)
            os.close(saved)
            sink.seek(0)
            native = sink.read().decode("utf-8", "replace")
            sys.stderr.write(native)
    return result, [line for line in native.splitlines() if line.startswith("[ocr] ")]


def parse(args: argparse.Namespace) -> dict:
    """Parse the requested pages with the requested backend, or refuse."""

    if args.out is not None:
        check_output(args.out, [REPO, args.root])
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
        result, failures = parse_watching_stderr(parser, content)
    except ParseError as exc:
        raise Refused(f"liteparse could not parse {source['path']}: {exc}") from exc
    if failures:
        raise Refused(
            f"liteparse reported failed OCR ({' / '.join(failures)}); it returns such"
            " a page anyway, as if it had no text, so no report is written"
        )
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
        "library_config": {
            key: getattr(config, field) for key, field in REPORTED.items()
        },
        "model": model,
        "source": {**source, "total_pages": result.total_pages},
        "pages": [page_record(page) for page in result.pages],
    }


def pull() -> dict:
    """Install ocria-nano through liteparse's checked pull, the only command that downloads, then
    check the installed files against the pins.

    The model repository is public. liteparse would send HF_TOKEN, or the token stored under
    HF_HOME, so the pull runs without the first and with the second naming an empty directory.
    What could not be verified afterwards (the platform, a runtime or loader override) is refused
    before anything is downloaded, so no cache is replaced in vain.
    """

    check_runtime_environment()
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
        "--out",
        type=Path,
        default=None,
        help="a new file for the JSON: outside the repository or under"
        " tools/commentary_rag/local/ (default: stdout)",
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
        text = json.dumps(report, ensure_ascii=False, indent=1)
        if getattr(args, "out", None) is None:
            print(text)
            return 0
        try:
            with args.out.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text + "\n")
        except FileExistsError as exc:
            raise Refused(
                f"--out {args.out} appeared meanwhile; it is not replaced"
            ) from exc
        except OSError as exc:
            raise Refused(f"--out {args.out}: {exc.strerror}") from exc
    except Refused as exc:
        print(f"liteparse_ocr refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
