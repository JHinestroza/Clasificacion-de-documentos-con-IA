"""The database probe enforces TLS and performs no writes."""

from unittest.mock import MagicMock, patch

import pytest

from document_platform.config import Settings
from document_platform.infrastructure.persistence.connection import check_postgres


def test_probe_requires_tls_and_verifies_server_identity(settings: Settings) -> None:
    with patch(
        "document_platform.infrastructure.persistence.connection.psycopg.connect"
    ) as connect:
        connection = connect.return_value.__enter__.return_value
        connection.pgconn.ssl_in_use = True
        connection.execute.return_value.fetchone.side_effect = [(1,), (True,)]
        check_postgres(settings)
        assert connect.call_args.kwargs["sslmode"] == "verify-full"
        assert connect.call_args.kwargs["sslrootcert"] == str(settings.tls_ca_file)
        assert connect.call_args.kwargs["ssl_min_protocol_version"] == "TLSv1.2"
        assert connect.call_args.kwargs["gssencmode"] == "disable"
        assert connection.execute.call_count == 2
        assert connection.execute.call_args_list[0].args == ("SELECT 1",)


def test_probe_rejects_non_tls_connection(settings: Settings) -> None:
    connection = MagicMock()
    connection.pgconn.ssl_in_use = False
    with patch(
        "document_platform.infrastructure.persistence.connection.psycopg.connect"
    ) as connect:
        connect.return_value.__enter__.return_value = connection
        with pytest.raises(ConnectionError, match="did not use TLS"):
            check_postgres(settings)
        connection.execute.assert_not_called()


def test_probe_rejects_missing_identity_migration(settings: Settings) -> None:
    with patch(
        "document_platform.infrastructure.persistence.connection.psycopg.connect"
    ) as connect:
        connection = connect.return_value.__enter__.return_value
        connection.pgconn.ssl_in_use = True
        connection.execute.return_value.fetchone.side_effect = [(1,), (False,)]
        with pytest.raises(ConnectionError, match="migrations"):
            check_postgres(settings)
