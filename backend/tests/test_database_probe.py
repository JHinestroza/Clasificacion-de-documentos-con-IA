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
        connection.execute.return_value.fetchone.return_value = (1,)
        check_postgres(settings)
        assert connect.call_args.kwargs["sslmode"] == "verify-full"
        assert connect.call_args.kwargs["sslrootcert"] == str(settings.tls_ca_file)
        assert connect.call_args.kwargs["ssl_min_protocol_version"] == "TLSv1.2"
        assert connect.call_args.kwargs["gssencmode"] == "disable"
        connection.execute.assert_called_once_with("SELECT 1")


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
