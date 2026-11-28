"""Offline tests for liteparse_ocr.py, the opt-in LiteParse / OCRia-nano-1 diagnostic.

liteparse is in no environment of this repository, so every test replaces it at the module's
import seam (``LiteParse``, ``ParseError``, ``models`` and the version lookup) with a stand-in
that records what the tool asked for, and replaces the asset pins and the platform with ones that
fit a two-file synthetic package. Nothing is downloaded and nothing is parsed: the PDF bytes are
synthetic and only their SHA-256 matters, the page text is made up. The stand-in parser can write
to file descriptor 2, the only place liteparse reports a page whose OCR failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import liteparse_ocr

PDF = b"%PDF-1.7\n% synthetic bytes: the stand-in parser never reads them\n"
EDITION = "2031-07-01"
NANO = "ocria-nano"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# the synthetic package of package() below, pinned the way the tool pins ocria-nano 1.0.0
PINS = {
    "det.onnx": (8, sha(b"detector")),
    "runtime/libonnxruntime.dylib": (7, sha(b"runtime")),
}
HOST = (sys.platform, platform.machine())
# The OCRia-nano path refuses any variable named DYLD_* or LD_*, and ORT_DYLIB_PATH, when present
# at all, even empty: the names known today and ones no list could foresee.
LOADER = [
    "ORT_DYLIB_PATH",
    "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "DYLD_VERSIONED_LIBRARY_PATH",
    "DYLD_IMAGE_SUFFIX",
    "DYLD_NOT_NAMED_YET",
    "LD_AUDIT",
    "LD_NOT_NAMED_YET",
]


class FakeParseError(Exception):
    """Stands in for liteparse.ParseError."""


class FakeModels:
    """Stands in for liteparse.models: what is installed, and a pull that only records."""

    def __init__(self) -> None:
        self.installed: list[SimpleNamespace] = []
        self.pulled: list[str] = []
        self.credentials: list[tuple] = []
        self.seen_dirs: list[
            str | None
        ] = []  # LITEPARSE_MODEL_DIR when list() was asked
        self.pulled_into: list[str | None] = []  # LITEPARSE_MODEL_DIR when pull() ran

    def list(self) -> list[SimpleNamespace]:
        """The installed packages, as liteparse.models.list() returns them."""
        self.seen_dirs.append(os.environ.get("LITEPARSE_MODEL_DIR"))
        return list(self.installed)

    def pull(
        self, spec: str, *, from_dir: str | None = None, quiet: bool = False
    ) -> str:
        """Record the request and the Hugging Face credentials liteparse could have sent."""
        self.pulled.append(spec)
        self.pulled_into.append(os.environ.get("LITEPARSE_MODEL_DIR"))
        home = os.environ.get("HF_HOME")
        stored = sorted(os.listdir(home)) if home else None
        self.credentials.append((os.environ.get("HF_TOKEN"), home is not None, stored))
        return "/models/ocria-nano"


class Library:
    """One stand-in liteparse per test: its parser class, its models and what it reports."""

    def __init__(self) -> None:
        self.models = FakeModels()
        self.built: list = []
        self.report: dict = {}
        self.pages = [page(3)]
        self.total_pages = 4
        self.error: Exception | None = None
        self.native_stderr = b""  # what the native parse writes to file descriptor 2
        self.parse_dirs: list[str | None] = []  # LITEPARSE_MODEL_DIR when parse() ran
        library = self

        class Parser:
            def __init__(self, **options) -> None:
                self.options = options
                self.parsed: list[bytes] = []
                library.built.append(self)

            def get_config(self) -> None:
                """As in liteparse 2.21.4: its native config lacks keep_clipped_text."""
                raise AttributeError(
                    "'builtins.PyLiteParseConfig' object has no attribute"
                    " 'keep_clipped_text'"
                )

            @property
            def _native(self) -> SimpleNamespace:
                """The native parser; its config holds the resolved values, unless overridden."""
                resolved = {
                    "ocr_enabled": self.options.get("ocr_enabled", True),
                    "ocr_backend": self.options.get("ocr_backend") or "tesseract",
                    "dpi": 150.0,
                    "table_model": None,
                    "ocr_failure_fatal": True,
                    "target_pages": self.options.get("target_pages"),
                }
                resolved.update(library.report)
                return SimpleNamespace(config=SimpleNamespace(**resolved))

            def parse(self, data: bytes) -> SimpleNamespace:
                """Return the test's pages, or raise the test's error."""
                self.parsed.append(data)
                library.parse_dirs.append(os.environ.get("LITEPARSE_MODEL_DIR"))
                if library.native_stderr:
                    os.write(2, library.native_stderr)
                if library.error is not None:
                    raise library.error
                return SimpleNamespace(
                    pages=library.pages, total_pages=library.total_pages
                )

        self.parser = Parser


@pytest.fixture
def lib(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Library:
    library = Library()
    monkeypatch.setattr(liteparse_ocr, "LiteParse", library.parser)
    monkeypatch.setattr(liteparse_ocr, "ParseError", FakeParseError)
    monkeypatch.setattr(liteparse_ocr, "models", library.models)
    monkeypatch.setattr(liteparse_ocr, "liteparse_version", lambda: "9.9.9")
    monkeypatch.setattr(liteparse_ocr, "PACKAGE", PINS, raising=False)
    monkeypatch.setattr(liteparse_ocr, "PLATFORM", HOST, raising=False)
    inherited = [
        n for n in os.environ if n.startswith(("DYLD_", "LD_")) or n == "ORT_DYLIB_PATH"
    ]
    for name in inherited:  # a runner's environment must not decide a test
        monkeypatch.delenv(name)
    # absolute, and where package() installs
    monkeypatch.setenv("LITEPARSE_MODEL_DIR", str(tmp_path / "models"))
    return library


def item(text: str, *, confidence: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        x=10.0,
        y=20.0,
        width=30.0,
        height=8.0,
        font_name="Synthetic-Bold",
        font_size=1.0,
        font_height=11.0,
        font_weight=700,
        confidence=confidence,
    )


def block(text: str | None, kind: str = "paragraph", **fields) -> SimpleNamespace:
    """A block with every field of liteparse 2.21.4's LayoutBlock; ``fields`` override."""
    shape = {
        "kind": kind,
        "text": text,
        "level": None,
        "bold": False,
        "italic": False,
        "ordered": None,
        "marker": None,
        "lines": None,
        "lang": None,
        "header": None,
        "rows": None,
        "id": None,
        "format": None,
        "bbox": SimpleNamespace(x=10.0, y=20.0, width=30.0, height=8.0),
        "text_item_indices": [0],
    }
    return SimpleNamespace(**{**shape, **fields})


def cell(text: str, x: float | None) -> SimpleNamespace:
    """A table cell; ``x=None`` is a padding cell without ink (no box, no text items)."""
    if x is None:
        return SimpleNamespace(text=text, bbox=None, text_item_indices=[])
    return SimpleNamespace(
        text=text,
        bbox=SimpleNamespace(x=x, y=40.0, width=20.0, height=6.0),
        text_item_indices=[1],
    )


def page(number: int, items=(), blocks=()) -> SimpleNamespace:
    return SimpleNamespace(
        page_num=number,
        page_label=None,
        width=595.32,
        height=841.92,
        text_items=list(items),
        blocks=list(blocks),
    )


def package(
    tmp_path: Path, *, complete: bool = True, base: Path | None = None
) -> SimpleNamespace:
    """An installed ocria-nano package with two synthetic files, as models.list() reports it;
    under ``base`` (default: the fixture's LITEPARSE_MODEL_DIR, tmp_path/models)."""
    folder = (base or tmp_path / "models") / NANO
    (folder / "runtime").mkdir(parents=True)
    (folder / "det.onnx").write_bytes(b"detector")
    (folder / "runtime" / "libonnxruntime.dylib").write_bytes(b"runtime")
    return SimpleNamespace(
        name=NANO, version="1.0.0", path=str(folder), size_bytes=15, complete=complete
    )


def a_pdf(tmp_path: Path) -> str:
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(PDF)
    return str(path)


def edition_tree(tmp_path: Path, shape: str, digest: str) -> tuple[Path, Path]:
    """A checkout root holding one commentary PDF and a manifest in one of the two layouts."""
    root = tmp_path / "root"
    pdf = root / "data" / "raw" / "commentary.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(PDF)
    entry = {"path": "data/raw/commentary.pdf", "sha256": digest}
    if shape == "sources":
        data = {
            "kind": "commentary_sources",
            "sources": [{**entry, "effective_dates": [EDITION]}],
        }
    else:
        data = {
            "editions": [
                {
                    "effective_date": EDITION,
                    "documents": [
                        {
                            **entry,
                            "kind": "full_list_xlsx",
                            "path": "data/raw/list.xlsx",
                        },
                        {**entry, "kind": "commentary_pdf"},
                    ],
                }
            ]
        }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return root, manifest


def run(*argv: str) -> int:
    return liteparse_ocr.main(list(argv))


def nano(pdf: str, *extra: str) -> int:
    return run("parse", "--pdf", pdf, "--ocr-backend", NANO, *extra)


def test_the_backend_must_be_chosen_explicitly(lib, tmp_path, capsys) -> None:
    with pytest.raises(SystemExit) as stop:
        run("parse", "--pdf", a_pdf(tmp_path))
    assert stop.value.code == 2
    assert "--ocr-backend" in capsys.readouterr().err
    assert lib.built == []


def test_tesseract_is_not_one_of_the_choices(lib, tmp_path, capsys) -> None:
    with pytest.raises(SystemExit) as stop:
        run("parse", "--pdf", a_pdf(tmp_path), "--ocr-backend", "tesseract")
    assert stop.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert lib.built == []


@pytest.mark.parametrize("source", [[], ["--pdf", "a.pdf", "--edition", EDITION]])
def test_the_input_is_one_pdf_or_one_edition(lib, source, capsys) -> None:
    with pytest.raises(SystemExit) as stop:
        run("parse", *source, "--ocr-backend", NANO)
    assert stop.value.code == 2
    assert lib.built == []


@pytest.mark.parametrize("text", ["0", "-1", "3,x", ""])
def test_pages_are_positive_page_numbers(text) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        liteparse_ocr.page_list(text)


def test_pages_come_out_sorted_and_once() -> None:
    assert liteparse_ocr.page_list("4, 3,4") == [3, 4]


def test_without_liteparse_both_commands_exit_2_and_name_the_ephemeral_run(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(liteparse_ocr, "LiteParse", None)
    monkeypatch.setattr(liteparse_ocr, "models", None)
    assert nano(a_pdf(tmp_path)) == 2
    assert run("pull") == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.count("uv run --no-project --with liteparse==2.21.4") == 2


def test_a_missing_model_refuses_without_a_fallback_or_a_download(
    lib, tmp_path, capsys
) -> None:
    assert nano(a_pdf(tmp_path)) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "ocria-nano is not installed" in err
    assert "liteparse_ocr.py pull" in err
    assert lib.built == []  # no parser at all, so no other OCR engine either
    assert lib.models.pulled == []  # and nothing was downloaded


def test_an_incomplete_model_package_is_refused(lib, tmp_path, capsys) -> None:
    lib.models.installed = [package(tmp_path, complete=False)]
    assert nano(a_pdf(tmp_path)) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "incomplete" in err
    assert lib.built == []
    assert lib.models.pulled == []


def test_the_nano_path_names_its_backend_and_fails_loudly(lib, tmp_path) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.pages = [page(3), page(4)]
    assert nano(a_pdf(tmp_path), "--pages", "4,3") == 0
    options = lib.built[0].options
    assert options["ocr_enabled"] is True
    assert options["ocr_backend"] == NANO
    assert options["ocr_failure_fatal"] is True
    assert options["target_pages"] == "3,4"
    assert lib.built[0].parsed == [PDF]
    assert lib.models.pulled == []


def test_the_native_path_turns_ocr_off_and_keeps_the_model_package_out(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]  # installed, and still not used
    assert (
        run("parse", "--pdf", a_pdf(tmp_path), "--pages", "3", "--ocr-backend", "none")
        == 0
    )
    options = lib.built[0].options
    assert options["ocr_enabled"] is False
    # inert while OCR is off; it stops an installed ocria-nano from becoming the resolved backend
    assert options["ocr_backend"] == "tesseract"
    doc = json.loads(capsys.readouterr().out)
    assert doc["backend"] == "none"
    assert doc["model"] is None


def test_the_reported_backend_and_settings_come_from_the_parser(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.report = {"dpi": 250.0, "table_model": "/synthetic/tablenet.bin"}
    assert nano(a_pdf(tmp_path), "--pages", "3") == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["requested_backend"] == NANO
    assert doc["backend"] == NANO
    assert doc["library_config"]["dpi"] == 250.0
    # liteparse reports only an explicit table model there, never the one ocria-nano brings
    assert doc["library_config"]["table_model_override"] == "/synthetic/tablenet.bin"
    assert "table_model" not in doc["library_config"]
    assert doc["liteparse_version"] == "9.9.9"


@pytest.mark.parametrize(
    ("requested", "reported"),
    [
        (NANO, {"ocr_backend": "tesseract"}),
        (NANO, {"ocr_enabled": False}),
        ("none", {"ocr_enabled": True}),
    ],
)
def test_a_backend_the_parser_does_not_confirm_is_refused_before_parsing(
    lib, tmp_path, capsys, requested, reported
) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.report = reported
    assert run("parse", "--pdf", a_pdf(tmp_path), "--ocr-backend", requested) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "no fallback" in err
    assert lib.built[0].parsed == []


def test_each_item_and_block_keeps_its_source_page(lib, tmp_path, capsys) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.pages = [
        page(
            3,
            [item("Synthetic heading"), item("Position 1234.56", confidence=0.97)],
            [block("Synthetic heading", "heading")],
        ),
        page(4, [item("Synthetic body text")], [block("Synthetic body text")]),
    ]
    assert nano(a_pdf(tmp_path), "--pages", "3,4") == 0
    doc = json.loads(capsys.readouterr().out)
    pages = doc["pages"]
    assert [p["page"] for p in pages] == [3, 4]
    assert [(i["page"], i["text"]) for p in pages for i in p["text_items"]] == [
        (3, "Synthetic heading"),
        (3, "Position 1234.56"),
        (4, "Synthetic body text"),
    ]
    assert [(b["page"], b["kind"]) for p in pages for b in p["blocks"]] == [
        (3, "heading"),
        (4, "paragraph"),
    ]
    assert pages[0]["text_items"][0]["bbox"] == [10.0, 20.0, 40.0, 28.0]
    assert pages[0]["text_items"][1]["confidence"] == 0.97
    assert [p["ocr_items"] for p in pages] == [1, 0]


@pytest.mark.parametrize(("asked", "returned"), [("3", [1]), ("3,4", [3])])
def test_pages_the_request_did_not_name_or_get_are_refused(
    lib, tmp_path, capsys, asked, returned
) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.pages = [page(n) for n in returned]
    assert nano(a_pdf(tmp_path), "--pages", asked) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "attributed" in err


@pytest.mark.parametrize(("returned", "code"), [([1, 2], 0), ([1], 1)])
def test_without_pages_every_page_of_the_document_must_come_back(
    lib, tmp_path, capsys, returned, code
) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.total_pages = 2
    lib.pages = [page(n) for n in returned]
    assert nano(a_pdf(tmp_path)) == code
    assert "target_pages" not in lib.built[0].options
    out = capsys.readouterr().out
    assert (out == "") == bool(code)


@pytest.mark.parametrize("shape", ["sources", "editions"])
def test_an_edition_is_read_from_its_manifest_and_checked(
    lib, tmp_path, capsys, shape
) -> None:
    root, manifest = edition_tree(tmp_path, shape, sha(PDF))
    lib.models.installed = [package(tmp_path)]
    assert (
        run(
            "parse",
            "--edition",
            EDITION,
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--pages",
            "3",
            "--ocr-backend",
            NANO,
        )
        == 0
    )
    doc = json.loads(capsys.readouterr().out)
    assert doc["source"] == {
        "path": "data/raw/commentary.pdf",
        "sha256": sha(PDF),
        "edition": EDITION,
        "total_pages": 4,
    }
    assert lib.built[0].parsed == [PDF]  # the verified bytes, not a second read


def test_an_edition_whose_bytes_differ_from_the_manifest_is_refused(
    lib, tmp_path, capsys
) -> None:
    root, manifest = edition_tree(tmp_path, "sources", "0" * 64)
    lib.models.installed = [package(tmp_path)]
    assert (
        run(
            "parse",
            "--edition",
            EDITION,
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--ocr-backend",
            NANO,
        )
        == 1
    )
    assert "SHA-256" in capsys.readouterr().err
    assert lib.built == []


def test_the_model_identity_is_hashed_from_the_package_the_library_resolved(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 0
    model = json.loads(capsys.readouterr().out)["model"]
    assert (model["name"], model["version"], model["complete"]) == (NANO, "1.0.0", True)
    assert model["files"] == [
        {"file": "det.onnx", "bytes": 8, "sha256": sha(b"detector")},
        {"file": "runtime/libonnxruntime.dylib", "bytes": 7, "sha256": sha(b"runtime")},
    ]


def test_pull_is_the_one_command_that_downloads_and_it_pins_the_model_version(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [
        package(tmp_path)
    ]  # what models.list() shows after the pull
    assert run("pull") == 0
    assert lib.models.pulled == ["ocria-nano@1.0.0"]
    assert lib.built == []
    model = json.loads(capsys.readouterr().out)["model"]
    assert (model["name"], model["version"]) == (NANO, "1.0.0")


def test_pull_sends_no_hugging_face_token_and_leaves_the_environment_as_it_was(
    lib, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "synthetic-token")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf-home-with-a-stored-token"))
    lib.models.installed = [package(tmp_path)]
    assert run("pull") == 0
    # during the pull: no token variable, and HF_HOME names an empty directory
    assert lib.models.credentials == [(None, True, [])]
    assert os.environ["HF_TOKEN"] == "synthetic-token"
    assert os.environ["HF_HOME"] == str(tmp_path / "hf-home-with-a-stored-token")


def test_a_parse_error_is_refused_with_the_librarys_message(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.error = FakeParseError("synthetic: ocria-nano models not found")
    assert nano(a_pdf(tmp_path)) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "synthetic: ocria-nano models not found" in err


# Review round 1, P2: the model assets must match the pins before anything is parsed.


def test_the_pins_cover_the_sixteen_files_of_ocria_nano_1_0_0_on_macos_arm64() -> None:
    assert sorted(liteparse_ocr.PACKAGE) == [
        "LICENSE",
        "det.meta.json",
        "det.onnx",
        "manifest.json",
        "rec_cjk.charset.json",
        "rec_cjk.onnx",
        "rec_latin.charset.json",
        "rec_latin.onnx",
        "rec_rtl.charset.json",
        "rec_rtl.meta.json",
        "rec_rtl.onnx",
        "rec_world.charset.json",
        "rec_world.onnx",
        "router.onnx",
        "runtime/libonnxruntime.dylib",
        "tablenet.bin",
    ]
    assert liteparse_ocr.PACKAGE["runtime/libonnxruntime.dylib"] == (
        44830288,
        "2685dc296147c47b0dbd8e0615547b12fc0c445d158d1f374cbd0705d9626fdc",
    )
    assert liteparse_ocr.PLATFORM == ("darwin", "arm64")


def test_assets_that_match_their_pins_are_reported_as_matched(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 0
    model = json.loads(capsys.readouterr().out)["model"]
    assert model["assets_match_pins"] is True
    assert model["directory"] == str(tmp_path / "models")
    assert model["environment"] == {
        "refused_if_set": ["DYLD_*", "LD_*", "ORT_DYLIB_PATH"],
        "set": [],
    }
    assert "loader_overrides" not in model  # what the loader chose is never claimed


@pytest.mark.parametrize("change", ["altered", "missing", "extra", "version"])
def test_an_asset_that_does_not_match_its_pin_is_refused_before_parsing(
    lib, tmp_path, capsys, change
) -> None:
    entry = package(tmp_path)
    folder = Path(entry.path)
    if change == "altered":
        (folder / "det.onnx").write_bytes(b"detectoR")  # same size, other bytes
    elif change == "missing":
        (folder / "runtime" / "libonnxruntime.dylib").unlink()
    elif change == "extra":
        (folder / "rec_extra.onnx").write_bytes(b"unpinned")
    else:
        entry.version = "1.0.1"
    lib.models.installed = [entry]
    assert nano(a_pdf(tmp_path)) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "pin" in err
    assert lib.built == []


def test_a_runtime_named_by_ort_dylib_path_is_refused(
    lib, tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv("ORT_DYLIB_PATH", str(tmp_path / "libonnxruntime.dylib"))
    lib.models.installed = [package(tmp_path)]
    assert nano(a_pdf(tmp_path)) == 1
    assert "ORT_DYLIB_PATH" in capsys.readouterr().err
    assert lib.built == []


def test_a_platform_without_verified_pins_is_refused(
    lib, tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        liteparse_ocr, "this_platform", lambda: ("plan9", "mips"), raising=False
    )
    lib.models.installed = [package(tmp_path)]
    assert nano(a_pdf(tmp_path)) == 1
    assert "macOS arm64" in capsys.readouterr().err
    assert lib.built == []


# Review round 1, P2: tables, code and grids keep their content, each with its page.


def test_tables_code_and_grids_keep_their_cells_and_lines_with_their_page(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]
    table = block(
        None,
        "table",
        header=[cell("Code", 10.0), cell("Name", 30.0)],
        rows=[[cell("1234.56", 10.0), cell("", None)]],
    )
    code = block(
        None, "code", lines=["synthetic line one", "synthetic line two"], lang="text"
    )
    grid = block(None, "grid_fallback", lines=["a  b", "c  d"])
    entry = block("Synthetic item", "list_item", ordered=True, marker="1.", level=1)
    figure = block(None, "figure", id="7", format="png", text_item_indices=[])
    lib.pages = [
        page(3, [item("Code"), item("1234.56")], [table, code, grid, entry, figure])
    ]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 0
    blocks = json.loads(capsys.readouterr().out)["pages"][0]["blocks"]
    first = {
        "page": 3,
        "text": "Code",
        "bbox": [10.0, 40.0, 30.0, 46.0],
        "text_items": [1],
    }
    assert blocks[0]["header"][0] == first
    assert [c["text"] for c in blocks[0]["header"]] == ["Code", "Name"]
    assert blocks[0]["rows"] == [
        [
            {
                "page": 3,
                "text": "1234.56",
                "bbox": [10.0, 40.0, 30.0, 46.0],
                "text_items": [1],
            },
            {"page": 3, "text": "", "bbox": None, "text_items": []},
        ]
    ]
    assert (blocks[1]["lines"], blocks[1]["lang"]) == (
        ["synthetic line one", "synthetic line two"],
        "text",
    )
    assert blocks[2]["lines"] == ["a  b", "c  d"]
    assert (blocks[3]["ordered"], blocks[3]["marker"], blocks[3]["italic"]) == (
        True,
        "1.",
        False,
    )
    assert (blocks[4]["id"], blocks[4]["format"], blocks[4]["text_items"]) == (
        "7",
        "png",
        [],
    )
    assert {b["page"] for b in blocks} == {3}


# Review round 1, P2: a manifest may select only a file inside --root, never a link.


@pytest.mark.parametrize(
    ("where", "reason"),
    [
        ("parent", "outside --root"),
        ("absolute", "outside --root"),
        ("link out", "symbolic link"),
        ("link in", "symbolic link"),
    ],
)
def test_a_manifest_path_that_leaves_the_checkout_or_is_a_link_is_refused(
    lib, tmp_path, capsys, where, reason
) -> None:
    root = tmp_path / "root"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    outside = tmp_path / "private.pdf"
    outside.write_bytes(PDF)
    path = "data/raw/commentary.pdf"
    if where == "parent":
        path = "../private.pdf"
    elif where == "absolute":
        path = str(outside)
    elif where == "link out":
        (raw / "commentary.pdf").symlink_to(outside)
    else:
        (raw / "real.pdf").write_bytes(PDF)
        (raw / "commentary.pdf").symlink_to(raw / "real.pdf")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "kind": "commentary_sources",
                "sources": [
                    {"path": path, "sha256": sha(PDF), "effective_dates": [EDITION]}
                ],
            }
        ),
        encoding="utf-8",
    )
    lib.models.installed = [package(tmp_path)]
    assert (
        run(
            "parse",
            "--edition",
            EDITION,
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--ocr-backend",
            NANO,
        )
        == 1
    )
    out, err = capsys.readouterr()
    assert out == ""
    assert reason in err
    assert lib.built == []


# Review round 1, P2: an OCR failure that liteparse reports only on stderr fails the run.


def test_an_ocr_failure_reported_only_on_native_stderr_refuses_the_run(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.pages = [page(3), page(4, [item("Synthetic text", confidence=0.9)])]
    lib.native_stderr = (
        b"[ocr] failed for page 3: synthetic engine error\n"
        b"[ocr] 1/2 page(s) failed OCR; continuing with partial results\n"
    )
    assert nano(a_pdf(tmp_path), "--pages", "3,4") == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert (
        "[ocr] failed for page 3: synthetic engine error" in err
    )  # passed on as written
    assert "no report" in err


def test_a_page_without_ocr_text_and_without_a_failure_is_reported(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path)]
    lib.pages = [page(1), page(2, [item("Synthetic text", confidence=0.9)])]
    lib.total_pages = 2
    lib.native_stderr = b"[liteparse] ocr: 10.5ms\n"  # a log line, not a failure
    assert nano(a_pdf(tmp_path), "--pages", "1,2") == 0
    out, err = capsys.readouterr()
    assert [p["ocr_items"] for p in json.loads(out)["pages"]] == [0, 1]
    assert "[liteparse] ocr: 10.5ms" in err


# Review round 1, P3: an unreadable or malformed manifest is an input refusal naming it.


@pytest.mark.parametrize(
    "content", [None, "{not json", '{"sources": [{"path": 1}]}', "[]"]
)
def test_an_unreadable_or_malformed_manifest_is_refused_by_name(
    lib, tmp_path, capsys, content
) -> None:
    manifest = tmp_path / "broken-manifest.json"
    if content is not None:
        manifest.write_text(content, encoding="utf-8")
    assert (
        run(
            "parse",
            "--edition",
            EDITION,
            "--manifest",
            str(manifest),
            "--root",
            str(tmp_path),
            "--ocr-backend",
            NANO,
        )
        == 1
    )
    out, err = capsys.readouterr()
    assert out == ""
    assert "broken-manifest.json" in err
    assert lib.built == []


# Review round 2, P3: a manifest without either section, or with a path no file system can
# take, is refused by name.


def test_a_manifest_without_a_sources_or_editions_section_is_refused_by_name(
    lib, tmp_path, capsys
) -> None:
    root, manifest = edition_tree(tmp_path, "sources", sha(PDF))
    sectionless = tmp_path / "sectionless-manifest.json"
    sectionless.write_text("{}", encoding="utf-8")
    lib.models.installed = [package(tmp_path)]
    assert (
        run(
            "parse",
            "--edition",
            EDITION,
            "--manifest",
            str(manifest),
            "--manifest",
            str(sectionless),
            "--root",
            str(root),
            "--pages",
            "3",
            "--ocr-backend",
            NANO,
        )
        == 1
    )
    out, err = capsys.readouterr()
    assert out == ""
    assert "sectionless-manifest.json" in err
    assert lib.built == []


def test_a_manifest_path_with_an_embedded_nul_is_refused_by_name(
    lib, tmp_path, capsys
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    manifest = tmp_path / "nul-manifest.json"
    source = {
        "path": "data/raw/com\x00mentary.pdf",
        "sha256": sha(PDF),
        "effective_dates": [EDITION],
    }
    manifest.write_text(
        json.dumps({"kind": "commentary_sources", "sources": [source]}),
        encoding="utf-8",
    )
    lib.models.installed = [package(tmp_path)]
    assert (
        run(
            "parse",
            "--edition",
            EDITION,
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--ocr-backend",
            NANO,
        )
        == 1
    )
    out, err = capsys.readouterr()
    assert out == ""
    assert "nul-manifest.json" in err
    assert lib.built == []


# Review round 3: there is no output option; the report goes to stdout only.


def test_out_is_no_longer_an_option(lib, tmp_path, capsys) -> None:
    lib.models.installed = [package(tmp_path)]
    with pytest.raises(SystemExit) as stop:
        nano(a_pdf(tmp_path), "--pages", "3", "--out", str(tmp_path / "report.json"))
    assert stop.value.code == 2
    assert "--out" in capsys.readouterr().err
    assert not (tmp_path / "report.json").exists()
    assert lib.built == []


# Review round 3: any DYLD_* or LD_* variable, or ORT_DYLIB_PATH, set even empty, is refused.


@pytest.mark.parametrize(
    "override", [(name, value) for name in LOADER for value in ("", "/elsewhere")]
)
def test_a_runtime_or_loader_variable_is_refused_by_its_prefix_even_when_empty(
    lib, tmp_path, capsys, monkeypatch, override
) -> None:
    name, value = override
    monkeypatch.setenv(name, value)
    lib.models.installed = [package(tmp_path)]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 1
    assert name in capsys.readouterr().err
    assert lib.built == []


# Review round 3: one absolute model directory, resolved first, used by the checks and liteparse.


@pytest.mark.parametrize("value", ["", "models", "./models"])
def test_an_empty_or_relative_model_directory_is_refused_before_liteparse_is_asked(
    lib, tmp_path, capsys, monkeypatch, value
) -> None:
    monkeypatch.setenv("LITEPARSE_MODEL_DIR", value)
    monkeypatch.chdir(tmp_path)  # a relative folder would find the package here
    lib.models.installed = [package(tmp_path)]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 1
    err = capsys.readouterr().err
    assert "LITEPARSE_MODEL_DIR" in err
    assert "absolute" in err
    assert lib.models.seen_dirs == []
    assert lib.built == []


def test_without_a_model_dir_the_default_under_home_is_used_and_handed_to_liteparse(
    lib, tmp_path, capsys, monkeypatch
) -> None:
    home = tmp_path / "home"
    default = home / ".cache" / "liteparse" / "models"
    monkeypatch.delenv("LITEPARSE_MODEL_DIR")
    monkeypatch.setenv("HOME", str(home))
    lib.models.installed = [package(tmp_path, base=default)]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 0
    assert json.loads(capsys.readouterr().out)["model"]["directory"] == str(default)
    assert lib.models.seen_dirs == [str(default)]  # liteparse listed this very folder
    assert lib.parse_dirs == [str(default)]  # and parsed with it set


def test_without_a_model_dir_or_home_the_ocr_path_is_refused(
    lib, tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.delenv("LITEPARSE_MODEL_DIR")
    monkeypatch.delenv("HOME", raising=False)
    lib.models.installed = [package(tmp_path)]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 1
    assert "HOME" in capsys.readouterr().err
    assert lib.built == []


def test_a_package_liteparse_lists_outside_the_resolved_directory_is_refused(
    lib, tmp_path, capsys
) -> None:
    lib.models.installed = [package(tmp_path, base=tmp_path / "elsewhere")]
    assert nano(a_pdf(tmp_path), "--pages", "3") == 1
    assert "elsewhere" in capsys.readouterr().err
    assert lib.built == []


def test_the_native_path_needs_no_model_directory_or_package(
    lib, tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.delenv("LITEPARSE_MODEL_DIR")
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setenv("LD_PRELOAD", "")  # no ONNX Runtime is loaded without OCR
    assert (
        run("parse", "--pdf", a_pdf(tmp_path), "--pages", "3", "--ocr-backend", "none")
        == 0
    )
    assert json.loads(capsys.readouterr().out)["model"] is None
    assert lib.models.seen_dirs == []


def test_the_missing_model_message_names_the_absolute_directory_and_suggests_pull(
    lib, tmp_path, capsys
) -> None:
    assert nano(a_pdf(tmp_path)) == 1
    err = capsys.readouterr().err
    assert str(tmp_path / "models") in err
    assert "liteparse_ocr.py pull" in err


def test_an_unsupported_platform_is_refused_before_a_missing_model_is_mentioned(
    lib, tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.setattr(
        liteparse_ocr, "this_platform", lambda: ("plan9", "mips"), raising=False
    )
    assert nano(a_pdf(tmp_path)) == 1  # and no model is installed either
    err = capsys.readouterr().err
    assert "macOS arm64" in err
    assert "pull" not in err


# Review round 3: pull refuses before downloading what it could not verify, then checks the pins.


@pytest.mark.parametrize(
    "hazard",
    [
        "platform",
        "loader variable",
        "empty model directory",
        "relative model directory",
        "no home",
    ],
)
def test_pull_refuses_before_downloading_what_it_could_not_verify(
    lib, tmp_path, capsys, monkeypatch, hazard
) -> None:
    if hazard == "platform":
        monkeypatch.setattr(
            liteparse_ocr, "this_platform", lambda: ("plan9", "mips"), raising=False
        )
    elif hazard == "loader variable":
        monkeypatch.setenv("DYLD_VERSIONED_LIBRARY_PATH", "")
    elif hazard == "empty model directory":
        monkeypatch.setenv("LITEPARSE_MODEL_DIR", "")
    elif hazard == "relative model directory":
        monkeypatch.setenv("LITEPARSE_MODEL_DIR", "models")
    else:
        monkeypatch.delenv("LITEPARSE_MODEL_DIR")
        monkeypatch.delenv("HOME", raising=False)
    lib.models.installed = [package(tmp_path)]
    assert run("pull") == 1
    assert lib.models.pulled == []  # nothing downloaded, no cache replaced
    assert capsys.readouterr().out == ""


def test_pull_installs_into_the_one_absolute_model_directory(
    lib, tmp_path, capsys, monkeypatch
) -> None:
    home = tmp_path / "home"
    default = home / ".cache" / "liteparse" / "models"
    monkeypatch.delenv("LITEPARSE_MODEL_DIR")
    monkeypatch.setenv("HOME", str(home))
    lib.models.installed = [package(tmp_path, base=default)]
    assert run("pull") == 0
    assert lib.models.pulled_into == [str(default)]
    assert json.loads(capsys.readouterr().out)["model"]["directory"] == str(default)


def test_pull_checks_the_pins_after_the_download(lib, tmp_path, capsys) -> None:
    entry = package(tmp_path)
    (Path(entry.path) / "det.onnx").write_bytes(b"detectoR")  # same size, other bytes
    lib.models.installed = [entry]
    assert run("pull") == 1
    assert lib.models.pulled == ["ocria-nano@1.0.0"]  # downloaded, then refused
    out, err = capsys.readouterr()
    assert out == ""
    assert "det.onnx" in err


# Review round 3: a manifest section that is not a list is refused by name.


@pytest.mark.parametrize(
    "bad",
    [
        '{"sources": {}}',
        '{"editions": {}}',
        '{"editions": [{"effective_date": "2031-07-01", "documents": {}}]}',
    ],
)
def test_a_manifest_section_that_is_not_a_list_is_refused_by_name(
    lib, tmp_path, capsys, bad
) -> None:
    root, manifest = edition_tree(tmp_path, "sources", sha(PDF))
    unlisted = tmp_path / "unlisted-manifest.json"
    unlisted.write_text(bad, encoding="utf-8")
    lib.models.installed = [package(tmp_path)]
    assert (
        run(
            "parse",
            "--edition",
            EDITION,
            "--manifest",
            str(manifest),
            "--manifest",
            str(unlisted),
            "--root",
            str(root),
            "--pages",
            "3",
            "--ocr-backend",
            NANO,
        )
        == 1
    )
    out, err = capsys.readouterr()
    assert out == ""
    assert "unlisted-manifest.json" in err
    assert lib.built == []


# Review round 4, P3: a manifest with both sections has both validated, so a valid sources
# section cannot hide a malformed editions section; sources keeps its precedence.

SOURCE = {
    "path": "data/raw/commentary.pdf",
    "sha256": sha(PDF),
    "effective_dates": [EDITION],
}


def parse_edition(root: Path, *manifests: Path) -> int:
    argv = ["parse", "--edition", EDITION]
    for manifest in manifests:
        argv += ["--manifest", str(manifest)]
    return run(*argv, "--root", str(root), "--pages", "3", "--ocr-backend", NANO)


@pytest.mark.parametrize(
    ("sources", "editions"),
    [
        ([], {}),  # the edition comes from the other manifest
        ([SOURCE], {}),
        ([SOURCE], [{"effective_date": EDITION}]),
        (
            [SOURCE],
            [
                {
                    "effective_date": EDITION,
                    "documents": [
                        {"kind": "commentary_pdf", "path": 1, "sha256": sha(PDF)}
                    ],
                }
            ],
        ),
        (
            [SOURCE],
            [
                {
                    "effective_date": EDITION,
                    "documents": [
                        {
                            "kind": "commentary_pdf",
                            "path": "data/raw/com\x00mentary.pdf",
                            "sha256": sha(PDF),
                        }
                    ],
                }
            ],
        ),
    ],
    ids=["empty-sources", "editions-not-a-list", "edition-without-documents",
         "path-not-a-string", "path-with-nul"],
)
def test_a_valid_sources_section_does_not_hide_malformed_editions(
    lib, tmp_path, capsys, sources, editions
) -> None:
    root, other = edition_tree(tmp_path, "sources", sha(PDF))
    mixed = tmp_path / "mixed-manifest.json"
    mixed.write_text(
        json.dumps({"kind": "commentary_sources", "sources": sources, "editions": editions}),
        encoding="utf-8",
    )
    lib.models.installed = [package(tmp_path)]
    manifests = (other, mixed) if not sources else (mixed,)
    assert parse_edition(root, *manifests) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "mixed-manifest.json" in err
    assert "editions" in err
    assert lib.built == []


def test_with_both_sections_valid_the_pdf_still_comes_from_sources(
    lib, tmp_path, capsys
) -> None:
    """Characterization, true before and after the round-4 fix: sources keeps its precedence,
    and an editions document of another kind is not checked."""
    root, _ = edition_tree(tmp_path, "sources", sha(PDF))
    other = root / "data" / "raw" / "other.pdf"
    other.write_bytes(b"%PDF-1.7 another file")
    mixed = tmp_path / "mixed-manifest.json"
    editions = [
        {
            "effective_date": EDITION,
            "documents": [
                {"kind": "full_list_xlsx"},
                {
                    "kind": "commentary_pdf",
                    "path": "data/raw/other.pdf",
                    "sha256": sha(other.read_bytes()),
                },
            ],
        }
    ]
    mixed.write_text(
        json.dumps({"sources": [SOURCE], "editions": editions}), encoding="utf-8"
    )
    lib.models.installed = [package(tmp_path)]
    assert parse_edition(root, mixed) == 0
    assert json.loads(capsys.readouterr().out)["source"]["path"] == SOURCE["path"]
    assert lib.built[0].parsed == [PDF]


# Review round 4, P3: the report does not depend on the stdout encoding. Checked at the command
# line: the script runs in a child process, its stdout redirected into a file, against a
# stand-in liteparse package on PYTHONPATH (with its distribution metadata, which the version
# lookup reads).

SCRIPT = Path(__file__).resolve().parent / "liteparse_ocr.py"
STAND_IN = '''
import sys
from types import SimpleNamespace

print("stdout encoding:", sys.stdout.encoding, file=sys.stderr)


class ParseError(Exception):
    pass


class _Models:
    def list(self):
        return []

    def pull(self, spec, **options):
        raise RuntimeError("the stand-in downloads nothing")


models = _Models()


class LiteParse:
    def __init__(self, **options):
        config = SimpleNamespace(
            ocr_enabled=options["ocr_enabled"],
            ocr_backend=options["ocr_backend"],
            dpi=150.0,
            table_model=None,
            ocr_failure_fatal=True,
            target_pages=options.get("target_pages"),
        )
        self._native = SimpleNamespace(config=config)

    def parse(self, data):
        item = SimpleNamespace(
            text=TEXT, x=10.0, y=20.0, width=30.0, height=8.0, font_name="Synthetic",
            font_size=1.0, font_height=11.0, font_weight=400, confidence=None,
        )
        page = SimpleNamespace(
            page_num=1, page_label=None, width=595.32, height=841.92,
            text_items=[item], blocks=[],
        )
        return SimpleNamespace(pages=[page], total_pages=1)
'''
GERMAN = "Zuschlag für Überzeit, Größe"  # in Windows-1252, not in ASCII


def command_line(
    tmp_path: Path, text: str, encoding: str, *argv: str
) -> tuple[subprocess.CompletedProcess, bytes]:
    """Run the script as a command with stdout redirected into a file; return the process and
    the file's bytes."""
    site = tmp_path / "site"
    (site / "liteparse").mkdir(parents=True)
    (site / "liteparse" / "__init__.py").write_text(
        f"TEXT = {text!r}\n" + STAND_IN, encoding="utf-8"
    )
    (site / "liteparse-2.21.4.dist-info").mkdir()
    (site / "liteparse-2.21.4.dist-info" / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: liteparse\nVersion: 2.21.4\n", encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(
        PYTHONPATH=str(site), PYTHONIOENCODING=encoding, PYTHONDONTWRITEBYTECODE="1"
    )
    report = tmp_path / "report.json"
    with report.open("wb") as sink:
        done = subprocess.run(
            [sys.executable, str(SCRIPT), *argv],
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.PIPE,
            env=env,
            timeout=120,
            check=False,
        )
    return done, report.read_bytes()


@pytest.mark.parametrize(
    ("encoding", "text"),
    [("ascii", GERMAN), ("cp1252", GERMAN), ("utf-16", GERMAN), ("ascii", "Zuschlag")],
    ids=["ascii", "cp1252", "utf-16", "ascii-text-control"],
)
def test_the_report_reads_as_utf8_json_whatever_the_stdout_encoding(
    tmp_path, encoding, text
) -> None:
    done, raw = command_line(
        tmp_path, text, encoding, "parse", "--pdf", a_pdf(tmp_path), "--ocr-backend", "none"
    )
    err = done.stderr.decode(encoding, "replace")  # stderr follows the same setting
    assert f"stdout encoding: {encoding}" in err  # the setting reached the child
    assert done.returncode == 0, err
    report = json.loads(raw.decode("utf-8"))
    assert report["pages"][0]["text_items"][0]["text"] == text


def test_a_refusal_under_an_ascii_stdout_still_exits_1_with_nothing_on_stdout(
    tmp_path,
) -> None:
    missing = tmp_path / "fehlt-ü.pdf"
    done, raw = command_line(
        tmp_path, GERMAN, "ascii", "parse", "--pdf", str(missing), "--ocr-backend", "none"
    )
    assert done.returncode == 1
    assert raw == b""
    assert "liteparse_ocr refused:" in done.stderr.decode("utf-8", "replace")
