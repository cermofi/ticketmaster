from __future__ import annotations

import logging

from ticketmaster.core.telemetry import init_sentry
from ticketmaster.services.jobs import worker_loop


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_sentry()
    worker_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
