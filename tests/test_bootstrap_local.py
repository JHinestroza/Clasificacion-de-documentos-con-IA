"""Exercise bootstrap integrity using synthetic development certificates."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from scripts.bootstrap_local import ASSET_PATHS, BootstrapError, bootstrap


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    output = tmp_path / "local-assets"
    bootstrap(output)
    return output


def snapshot(output: Path) -> dict[Path, str]:
    return {path: hashlib.sha256((output / path).read_bytes()).hexdigest() for path in ASSET_PATHS}


def test_rerun_preserves_certificates_credentials_and_hashes(assets: Path) -> None:
    before = snapshot(assets)
    assert bootstrap(assets) is False
    assert bootstrap(assets, check_only=True) is False
    assert snapshot(assets) == before


def test_incomplete_set_is_not_repaired_or_rotated(assets: Path) -> None:
    previous_password = (assets / "secrets/db_admin_password").read_bytes()
    (assets / "certs/api.key").unlink()
    with pytest.raises(BootstrapError, match="incomplete"):
        bootstrap(assets)
    assert not (assets / "certs/api.key").exists()
    assert (assets / "secrets/db_admin_password").read_bytes() == previous_password


def test_check_only_never_creates_assets(tmp_path: Path) -> None:
    target = tmp_path / "absent"
    with pytest.raises(BootstrapError, match="do not exist"):
        bootstrap(target, check_only=True)
    assert not target.exists()


def test_mismatched_server_key_is_rejected_without_repair(assets: Path) -> None:
    replacement = (assets / "certs/postgres.key").read_bytes()
    (assets / "certs/api.key").write_bytes(replacement)
    with pytest.raises(BootstrapError, match="invalid"):
        bootstrap(assets)
    assert (assets / "certs/api.key").read_bytes() == replacement


def test_certificate_signed_by_another_ca_is_rejected(assets: Path, tmp_path: Path) -> None:
    other = tmp_path / "other-authority"
    bootstrap(other)
    for suffix in ("crt", "key"):
        relative = Path(f"certs/api.{suffix}")
        (assets / relative).write_bytes((other / relative).read_bytes())
    with pytest.raises(BootstrapError, match="invalid"):
        bootstrap(assets, check_only=True)


def test_cli_does_not_print_credentials_or_private_keys(tmp_path: Path) -> None:
    output = tmp_path / "cli-assets"
    script = Path(__file__).resolve().parents[1] / "scripts/bootstrap_local.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output-dir", str(output)],
        check=True,
        capture_output=True,
    )
    combined = result.stdout + result.stderr
    assert b"PRIVATE KEY" not in combined
    for file in (output / "secrets").iterdir():
        assert file.read_bytes().strip() not in combined


def test_expired_certificate_requires_explicit_renewal(assets: Path) -> None:
    ca = x509.load_pem_x509_certificate((assets / "certs/ca.crt").read_bytes())
    ca_key = serialization.load_pem_private_key((assets / "certs/ca.key").read_bytes(), None)
    assert isinstance(ca_key, ec.EllipticCurvePrivateKey)
    original = x509.load_pem_x509_certificate((assets / "certs/api.crt").read_bytes())
    expired = (
        x509.CertificateBuilder()
        .subject_name(original.subject)
        .issuer_name(ca.subject)
        .public_key(original.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=2))
        .not_valid_after(datetime.now(UTC) - timedelta(days=1))
    )
    for extension in original.extensions:
        expired = expired.add_extension(extension.value, extension.critical)
    replacement = expired.sign(ca_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
    (assets / "certs/api.crt").write_bytes(replacement)
    with pytest.raises(BootstrapError, match="invalid"):
        bootstrap(assets)
    assert (assets / "certs/api.crt").read_bytes() == replacement
