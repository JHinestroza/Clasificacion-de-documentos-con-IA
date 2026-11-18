"""Synthetic file identity, no-replace publication and actual bounded PDF validation."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pypdf import PdfWriter

from document_platform.domain.ingestion.models import IntakeFault, document_code
from document_platform.infrastructure.storage.intake import IntakeStorage, fingerprint
from document_platform.infrastructure.storage.pdf import pdf_pages


def pdf(path: Path, pages: int = 1, encrypted: bool = False) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    if encrypted:
        writer.encrypt("synthetic-pdf-password")
    with path.open("wb") as stream:
        writer.write(stream)
    return path


@pytest.mark.parametrize(
    ("name", "code"), [("CAB01.pdf", "CAB01"), ("cab02.PDF", "CAB02"), ("AB_01-02.pdf", "AB_01-02")]
)
def test_codes_keep_zeros_and_canonical_case(name, code):
    assert document_code(name) == code


@pytest.mark.parametrize(
    "name",
    [
        "../CAB01.pdf",
        "CAB01.txt",
        "CAB 01.pdf",
        "ñ01.pdf",
        ".pdf",
        "CAB01.final.pdf",
        "a" * 65 + ".pdf",
    ],
)
def test_ambiguous_or_unsafe_codes_are_not_rewritten(name):
    with pytest.raises(IntakeFault):
        document_code(name)


def test_deposit_is_complete_preserves_original_and_never_replaces(tmp_path):
    storage = IntakeStorage(tmp_path / "private")
    source = pdf(tmp_path / "CAB01.pdf")
    target = storage.deposit(source, "UFM")
    assert target.read_bytes() == source.read_bytes()
    assert storage.candidates("UFM", 10)[0]["name"] == "CAB01.pdf"
    with pytest.raises(IntakeFault, match="move_conflict"):
        storage.deposit(source, "UFM")
    (target.parent / "unfinished.part").write_bytes(b"incomplete")
    assert len(storage.candidates("UFM", 10)) == 1


def test_move_reconciles_a_crash_after_rename(tmp_path):
    storage = IntakeStorage(tmp_path / "private")
    storage.ensure("UFM")
    src = storage.path("UFM/incoming/CAB01.pdf")
    pdf(src)
    proof = fingerprint(src)
    dest = "UFM/processing/" + uuid4().hex + ".pdf"
    storage.complete_move("UFM/incoming/CAB01.pdf", dest, proof)
    storage.complete_move("UFM/incoming/CAB01.pdf", dest, proof)
    assert not src.exists() and fingerprint(storage.path(dest)) == proof


def test_move_preserves_conflicting_destination_and_source(tmp_path):
    storage = IntakeStorage(tmp_path / "private")
    storage.ensure("UFM")
    src = pdf(storage.path("UFM/incoming/CAB01.pdf"))
    dst = storage.path("UFM/processing/occupied.pdf")
    dst.write_bytes(b"existing-content")
    before = src.read_bytes()
    with pytest.raises(IntakeFault, match="move_conflict"):
        storage.complete_move(
            "UFM/incoming/CAB01.pdf", "UFM/processing/occupied.pdf", fingerprint(src)
        )
    assert dst.read_bytes() == b"existing-content" and src.read_bytes() == before


def test_changed_candidate_is_preserved(tmp_path):
    storage = IntakeStorage(tmp_path / "private")
    storage.ensure("UFM")
    src = pdf(storage.path("UFM/incoming/CAB01.pdf"))
    before = fingerprint(src)
    with src.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(IntakeFault, match="changed"):
        storage.complete_move("UFM/incoming/CAB01.pdf", "UFM/processing/item.pdf", before)
    assert src.exists() and not storage.path("UFM/processing/item.pdf").exists()


@pytest.mark.parametrize(
    "relative",
    [
        "../incoming/CAB01.pdf",
        "UFM/incoming/../CAB01.pdf",
        "UFM/other/x.pdf",
        "UFM/incoming/C:x.pdf",
    ],
)
def test_path_does_not_escape_storage(tmp_path, relative):
    with pytest.raises(IntakeFault, match="unsafe_path"):
        IntakeStorage(tmp_path / "private").path(relative)


def test_real_pdf_child_and_limits(settings, tmp_path):
    assert pdf_pages(pdf(tmp_path / "valid.pdf"), settings) == 1
    with pytest.raises(IntakeFault, match="page_limit"):
        pdf_pages(
            pdf(tmp_path / "pages.pdf", 2), settings.model_copy(update={"intake_max_pages": 1})
        )
    with pytest.raises(IntakeFault, match="encrypted_pdf"):
        pdf_pages(pdf(tmp_path / "encrypted.pdf", encrypted=True), settings)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a PDF")
    with pytest.raises(IntakeFault, match="invalid_pdf"):
        pdf_pages(bad, settings)


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing-mode verification")
def test_active_writer_prevents_validation(tmp_path):
    storage = IntakeStorage(tmp_path / "private")
    storage.ensure("UFM")
    path = pdf(storage.path("UFM/incoming/CAB01.pdf"))
    with (
        path.open("ab"),
        pytest.raises(IntakeFault, match="busy"),
        storage.read_guard("UFM/incoming/CAB01.pdf"),
    ):
        pass


def test_actual_os_memory_limit_prevents_large_child_allocation():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from document_platform.pdf_probe import memory_limit; "
                "memory_limit(128);\n"
                "try: value=bytearray(300*1024*1024)\n"
                "except MemoryError: print('bounded')"
            ),
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0 and result.stdout.strip() == b"bounded"


def test_exact_100mb_boundary_and_oversize_rejection(tmp_path):
    storage = IntakeStorage(tmp_path / "private")
    storage.ensure("UFM")
    path = storage.path("UFM/incoming/CAB01.pdf")
    with path.open("wb") as stream:
        stream.seek(100_000_000 - 1)
        stream.write(b"0")
    assert storage.inspect("UFM/incoming/CAB01.pdf")[0] == 100_000_000
    with path.open("ab") as stream:
        stream.write(b"1")
    with pytest.raises(IntakeFault, match="too_large"):
        storage.inspect("UFM/incoming/CAB01.pdf")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction verification")
def test_actual_windows_junction_is_rejected_without_touching_target(tmp_path):
    storage = IntakeStorage(tmp_path / "private")
    storage.root.mkdir()
    target = tmp_path / "unrelated"
    target.mkdir()
    preserved = target / "preserved.txt"
    preserved.write_text("synthetic content", encoding="utf-8")
    script = tmp_path / "make-test-junction.ps1"
    script.write_text(
        (
            "param($testJunctionPath,$testTargetPath)\n"
            '$ErrorActionPreference="Stop"\n'
            "New-Item -ItemType Junction -Path $testJunctionPath -Target "
            "$testTargetPath | Out-Null"
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(script),
            str(storage.root / "UFM"),
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    with pytest.raises(IntakeFault, match="unsafe_path"):
        storage.ensure("UFM")
    assert preserved.read_text(encoding="utf-8") == "synthetic content"


def test_probe_deadline_survives_its_parent_exit():
    child = (
        "import time; from document_platform.pdf_probe import arm_deadline; "
        "arm_deadline(1); print('armed',flush=True); time.sleep(20); print('escaped')"
    )
    parent = (
        "import os,subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}],stdout=sys.stdout,stderr=sys.stderr); "
        "print('parent_exited',flush=True); os._exit(0)"
    )
    # The inherited pipe stays open until the orphan terminates itself.
    result = subprocess.run(
        [sys.executable, "-c", parent],
        capture_output=True,
        timeout=8,
        check=False,
    )
    assert result.returncode == 0
    assert b"armed" in result.stdout and b"parent_exited" in result.stdout
    assert b"escaped" not in result.stdout


def test_os_cpu_limit_terminates_a_runaway_probe():
    code = (
        "from document_platform.pdf_probe import memory_limit; memory_limit(128,1); "
        "print('cpu_bound_ready',flush=True)\nwhile True: pass"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert b"cpu_bound_ready" in result.stdout and result.returncode != 0
