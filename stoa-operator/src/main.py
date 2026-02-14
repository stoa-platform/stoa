"""STOA Operator entry point — kopf-based GitOps reconciliation operator."""

import logging

import kopf
from prometheus_client import start_http_server

from src.config import settings
from src.cp_client import cp_client
from src.metrics import OPERATOR_UP


def configure_logging() -> None:
    """Configure logging based on operator settings."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@kopf.on.startup()
async def on_startup(settings: kopf.OperatorSettings, **_kwargs: object) -> None:
    """Configure operator, start metrics server, and connect to CP API."""
    # Use status subresource for progress storage — avoids update → handler loops
    settings.persistence.progress_storage = kopf.StatusProgressStorage(
        field="status.kopf",
    )
    # Import handlers to register them with kopf
    import src.handlers.gateway_binding  # noqa: F401
    import src.handlers.gateway_instance  # noqa: F401
    from src.config import settings as op_settings

    start_http_server(op_settings.METRICS_PORT)
    OPERATOR_UP.set(1)

    await cp_client.connect()
    logging.getLogger(__name__).info(
        "STOA Operator started (metrics on :%d)", op_settings.METRICS_PORT
    )


@kopf.on.cleanup()
async def on_cleanup(**_kwargs: object) -> None:
    """Gracefully shut down the operator."""
    OPERATOR_UP.set(0)
    await cp_client.close()
    logging.getLogger(__name__).info("STOA Operator stopped")


def main() -> None:
    """Run the operator standalone."""
    configure_logging()
    kopf.run(standalone=True, clusterwide=False, namespace=None)


if __name__ == "__main__":
    main()
