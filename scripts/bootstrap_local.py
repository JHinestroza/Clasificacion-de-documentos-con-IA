"""Generate or verify the private TLS assets for the synthetic local environment.

This creates a development CA without installing it in the operating system trust
store. Filesystem permissions do not establish encryption at rest or Windows ACLs.
Existing assets are verified, never overwritten or silently rotated.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / ".local"
SERVICES = {
    "api": ("api", "localhost", "127.0.0.1"),
    "postgres": ("postgres",),
    "rabbitmq": ("rabbitmq",),
}
SECRET_NAMES = ("db_admin_password", "db_app_password", "broker_app_password")
ASSET_PATHS = (
    Path("certs/ca.crt"),
    Path("certs/ca.key"),
    *(Path(f"certs/{service}.{suffix}") for service in SERVICES for suffix in ("crt", "key")),
    *(Path("secrets") / name for name in SECRET_NAMES),
)


class BootstrapError(RuntimeError):
    """Local assets are incomplete or unsafe to use; no automatic repair occurs."""


def _name(label: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, label)])


def _pem_key(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public_key_bytes(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey) -> bytes:
    public_key = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    return public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _general_name(value: str) -> x509.DNSName | x509.IPAddress:
    try:
        return x509.IPAddress(ipaddress.ip_address(value))
    except ValueError:
        return x509.DNSName(value)


def _make_certificates(now: datetime) -> dict[Path, bytes]:
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = _name("Document Platform local development CA")
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    assets = {
        Path("certs/ca.crt"): ca.public_bytes(serialization.Encoding.PEM),
        Path("certs/ca.key"): _pem_key(ca_key),
    }
    for service, names in SERVICES.items():
        key = ec.generate_private_key(ec.SECP256R1())
        certificate = (
            x509.CertificateBuilder()
            .subject_name(_name(service))
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(x509.SubjectAlternativeName([_general_name(n) for n in names]), False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, False, False, False, False),
                True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
            )
            .sign(ca_key, hashes.SHA256())
        )
        assets[Path(f"certs/{service}.crt")] = certificate.public_bytes(serialization.Encoding.PEM)
        assets[Path(f"certs/{service}.key")] = _pem_key(key)
    return assets


def _validate_assets(assets: dict[Path, bytes], now: datetime) -> None:
    try:
        certificates: dict[str, x509.Certificate] = {}
        for label in ("ca", *SERVICES):
            certificate = x509.load_pem_x509_certificate(assets[Path(f"certs/{label}.crt")])
            key = serialization.load_pem_private_key(
                assets[Path(f"certs/{label}.key")], password=None
            )
            if not isinstance(key, ec.EllipticCurvePrivateKey):
                raise ValueError("unsupported key")
            public_key = certificate.public_key()
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                raise ValueError("unsupported public key")
            if _public_key_bytes(key) != _public_key_bytes(public_key):
                raise ValueError("key mismatch")
            if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc:
                raise ValueError("certificate expired or not yet valid")
            certificates[label] = certificate
        ca = certificates["ca"]
        ca.verify_directly_issued_by(ca)
        ca_constraints = ca.extensions.get_extension_for_class(x509.BasicConstraints)
        if not ca_constraints.critical or ca_constraints.value != x509.BasicConstraints(True, 0):
            raise ValueError("invalid CA constraints")
        if not ca.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign:
            raise ValueError("invalid CA key usage")
        for service, names in SERVICES.items():
            certificate = certificates[service]
            certificate.verify_directly_issued_by(ca)
            constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints)
            if not constraints.critical or constraints.value.ca:
                raise ValueError("invalid server constraints")
            sans = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            if set(sans) != {_general_name(name) for name in names}:
                raise ValueError("invalid server names")
            eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            if set(eku) != {ExtendedKeyUsageOID.SERVER_AUTH}:
                raise ValueError("invalid server usage")
        for name in SECRET_NAMES:
            value = assets[Path("secrets") / name]
            if not re.fullmatch(rb"[A-Za-z0-9_-]{64}\n", value):
                raise ValueError("invalid generated credential")
        if len({assets[Path("secrets") / name] for name in SECRET_NAMES}) != len(SECRET_NAMES):
            raise ValueError("credentials must be distinct")
    except (ValueError, TypeError, KeyError, x509.ExtensionNotFound, InvalidSignature) as exc:
        raise BootstrapError(
            "Local certificate or credential set is invalid; no files were changed."
        ) from exc


def _read_assets(output_dir: Path) -> dict[Path, bytes]:
    for directory in (output_dir, output_dir / "certs", output_dir / "secrets"):
        if directory.is_symlink() or not directory.is_dir():
            raise BootstrapError("Local asset directories are incomplete or symbolic links.")
    assets: dict[Path, bytes] = {}
    for relative in ASSET_PATHS:
        file = output_dir / relative
        if file.is_symlink() or not file.is_file():
            raise BootstrapError(
                "Local assets are incomplete; refusing to overwrite or regenerate them."
            )
        assets[relative] = file.read_bytes()
    return assets


def bootstrap(output_dir: Path = DEFAULT_OUTPUT, *, check_only: bool = False) -> bool:
    """Create assets once, or validate them without mutation; return whether created.

    A partial set is deliberately not repaired because doing so could rotate a
    credential while a database or broker still uses its previous value.
    """
    output_dir = Path(output_dir).absolute()
    now = datetime.now(UTC)
    if output_dir.is_symlink():
        raise BootstrapError("The local asset directory must not be a symbolic link.")
    if output_dir.exists():
        _validate_assets(_read_assets(output_dir), now)
        return False
    if check_only:
        raise BootstrapError("Local assets do not exist; run bootstrap first.")

    assets = _make_certificates(now)
    for name in SECRET_NAMES:
        assets[Path("secrets") / name] = (secrets.token_urlsafe(48) + "\n").encode("ascii")
    _validate_assets(assets, now)

    # Exclusive directory and file creation prevents accidental identity rotation.
    # An interrupted write leaves a partial set that subsequent runs reject.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(mode=0o700)
    (output_dir / "certs").mkdir(mode=0o700)
    (output_dir / "secrets").mkdir(mode=0o700)
    for relative, value in assets.items():
        target = output_dir / relative
        with target.open("xb") as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        target.chmod(0o644 if relative.suffix == ".crt" else 0o600)
    _validate_assets(_read_assets(output_dir), now)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check-only", action="store_true", help="Validate; do not create or change files."
    )
    args = parser.parse_args()
    try:
        created = bootstrap(args.output_dir, check_only=args.check_only)
    except BootstrapError as exc:
        print(f"Bootstrap refused: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("Bootstrap refused: local assets could not be accessed safely.", file=sys.stderr)
        return 1
    print(
        "Local development assets created."
        if created
        else "Local development assets verified; unchanged."
    )
    print(
        "No OS trust changes were made. Files remain subject to host ACLs and storage encryption."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
