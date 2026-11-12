"""Broker provisioning uses hashed credentials, stable identities and local TLS only."""

import json
import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from document_platform.config import Settings
from scripts import prepare_rabbitmq_local as setup
from scripts.bootstrap_local import bootstrap


def test_definitions_do_not_expose_password_or_admin_rights(settings: Settings) -> None:
    result = setup.definitions(settings)
    assert settings.broker_password.get_secret_value() not in json.dumps(result)
    assert result["users"][0]["tags"] == []
    assert result["permissions"][0]["configure"] == r"^document_platform[.]integration$"
    assert setup.definitions(settings, result) == result


def test_preparation_refuses_to_rotate_an_existing_credential(settings: Settings) -> None:
    result = setup.definitions(settings)
    modified = settings.model_copy(update={"broker_password": SecretStr("different-" + "x" * 64)})
    with pytest.raises(ValueError, match="conflict"):
        setup.definitions(modified, result)


def test_permissions_are_not_broadened_on_rerun(settings: Settings) -> None:
    result = setup.definitions(settings)
    result["permissions"][0]["read"] = ".*"
    with pytest.raises(ValueError, match="permissions differ"):
        setup.definitions(settings, result)


def test_server_config_disables_plain_amqp_and_binds_loopback(tmp_path: Path) -> None:
    config = setup.render_config(tmp_path / "service")
    assert "listeners.tcp = none" in config
    assert "listeners.ssl.1 = 127.0.0.1:5671" in config
    assert "ssl_options.verify = verify_peer" in config
    assert "definitions.import_backend = local_filesystem" in config
    assert "default_pass" not in config


@pytest.mark.parametrize("suffix", ["bad\npath", "bad#path"])
def test_config_paths_cannot_inject_settings(tmp_path: Path, suffix: str) -> None:
    with pytest.raises(ValueError):
        setup.render_config(tmp_path / suffix)


def test_tls_preparation_is_idempotent_and_preserves_originals(
    tmp_path: Path,
    settings_values: dict,
) -> None:
    # settings_values isolates environment variables; bootstrap creates a separate synthetic CA.
    local = tmp_path / ".local"
    bootstrap(local)
    settings = Settings(_env_file=tmp_path / ".env")
    originals = {file.name: file.read_bytes() for file in (local / "certs").iterdir()}
    output = setup.prepare(tmp_path, tmp_path / "service", settings)
    prepared = {file.name: file.read_bytes() for file in output.iterdir()}
    setup.prepare(tmp_path, tmp_path / "service", settings)
    assert {file.name: file.read_bytes() for file in output.iterdir()} == prepared
    assert {file.name: file.read_bytes() for file in (local / "certs").iterdir()} == originals
    (output / "server.key").unlink()
    with pytest.raises(ValueError, match="Incomplete"):
        setup.prepare(tmp_path, tmp_path / "service", settings)


def test_local_host_change_preserves_literal_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / ".env"
    literal = "literal-${DO_NOT_EXPAND}-" + "s" * 40
    path.write_text(f"# custom comment\nAPP_DB_PASSWORD='{literal}'\nAPP_BROKER_HOST=rabbitmq\n")
    setup.configure_local_environment(tmp_path)
    content = path.read_text()
    assert literal in content and "# custom comment" in content
    assert "APP_BROKER_HOST='localhost'" in content
    assert "APP_BROKER_PORT='5671'" in content
    before = path.read_bytes()
    setup.configure_local_environment(tmp_path)
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "nt", reason="Windows token identity guard")
def test_codex_operator_is_refused_before_preparing_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    def sandbox_name(buffer: object, length: object) -> int:
        buffer.value = "CodexSandboxOffline"
        return 1

    monkeypatch.setattr(setup.ctypes.windll.advapi32, "GetUserNameW", sandbox_name)
    with pytest.raises(RuntimeError, match="own Windows account"):
        setup.assert_operator()
