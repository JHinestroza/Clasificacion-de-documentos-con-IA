"""CLI for a real TLS broker probe; output excludes connection URLs and credentials."""

import argparse
import json

from document_platform.config import Settings
from document_platform.infrastructure.messaging.connection import check_broker
from document_platform.infrastructure.messaging.probe import (
    consume_probe,
    publish_probe,
    queue_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    commands.add_parser("status")
    publish = commands.add_parser("publish")
    publish.add_argument("--count", type=int, default=1, choices=range(1, 101), metavar="1..100")
    consume = commands.add_parser("consume")
    consume.add_argument("--limit", type=int, default=1, choices=range(1, 101), metavar="1..100")
    consume.add_argument("--requeue", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings()
        if args.command == "check":
            check_broker(settings)
            result = {"broker": "ok", "transport": "TLS", "hostname_verified": True}
        elif args.command == "status":
            result = queue_status(settings)
        elif args.command == "publish":
            result = publish_probe(settings, args.count)
        else:
            result = consume_probe(settings, args.limit, requeue=args.requeue)
    except Exception:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "Broker probe failed; check TLS, credentials and queue permissions.",
                }
            )
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
