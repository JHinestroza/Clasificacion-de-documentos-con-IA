"""Intake rules and bounded public causes; never include parser/transport diagnostics."""

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

Record = dict[str, Any]
CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
FINAL_ITEMS = frozenset({"admitted", "skipped", "failed"})
ACTIVE_BATCHES = frozenset({"running", "paused", "pause_requested", "stop_requested"})


class IntakeFault(Exception):
    """A stable cause code that may be stored or returned without sensitive detail."""


@dataclass(frozen=True)
class PdfFacts:
    size: int
    sha256: str
    pages: int


def document_code(name: str) -> str:
    if PurePath(name).name != name or not name.lower().endswith(".pdf"):
        raise IntakeFault("invalid_name")
    value = name[:-4]
    if not value.isascii() or CODE.fullmatch(value) is None:
        raise IntakeFault("invalid_name")
    return value.upper()


def reason_text(reason: str | None) -> str:
    return {
        "invalid_name": (
            "El nombre debe contener un código de 1 a 64 letras, números, guion o guion bajo."
        ),
        "invalid_pdf": "La estructura PDF no es válida.",
        "encrypted_pdf": "El PDF requiere contraseña.",
        "too_large": "El archivo supera los 100 MB.",
        "page_limit": "El PDF supera el límite de páginas.",
        "parser_limit": "La validación alcanzó su límite de tiempo o memoria.",
        "duplicate_code": "El código ya está registrado; se conservó esta entrega.",
        "same_content": "Se detectó contenido idéntico con otro código.",
        "batch_limit": "La carpeta supera el límite de documentos por lote configurado.",
        "busy": "El archivo está ocupado; se volverá a intentar.",
        "changed": "El archivo cambió después de iniciar el lote; requiere una nueva entrega.",
        "unsafe_path": "La ruta o el tipo de archivo no está permitido.",
        "move_conflict": (
            "El movimiento necesita revisión; se conservan las ubicaciones existentes."
        ),
        "storage_unavailable": "El archivo o almacenamiento no está disponible.",
        "access_revoked": "El operador perdió acceso; no se admiten nuevos documentos.",
        "broker_unavailable": "Publicación pendiente; RabbitMQ no confirmó la entrega.",
        "publication_blocked": (
            "Publicación detenida tras diez intentos; requiere reintento autorizado."
        ),
    }.get(reason or "", reason or "")
