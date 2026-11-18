"""Run structural parsing in a bounded child, without propagating document diagnostics."""

import json
import subprocess
import sys
from pathlib import Path

from document_platform.config import Settings
from document_platform.domain.ingestion.models import IntakeFault


def pdf_pages(path: Path, settings: Settings) -> int:
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "document_platform.pdf_probe",
                str(path),
                str(settings.intake_max_pages),
                str(settings.intake_parser_memory_mb),
                str(settings.intake_parser_seconds),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=settings.intake_parser_seconds,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0 or len(result.stdout) > 1024:
            raise IntakeFault("parser_limit")
        row = json.loads(result.stdout)
        if "reason" in row:
            raise IntakeFault(
                row["reason"]
                if row["reason"] in {"invalid_pdf", "encrypted_pdf", "parser_limit", "page_limit"}
                else "invalid_pdf"
            )
        pages = row.get("pages")
        if type(pages) is not int or not 0 < pages <= settings.intake_max_pages:
            raise IntakeFault("invalid_pdf")
        return pages
    except subprocess.TimeoutExpired:
        raise IntakeFault("parser_limit") from None
    except (ValueError, OSError):
        raise IntakeFault("invalid_pdf") from None
