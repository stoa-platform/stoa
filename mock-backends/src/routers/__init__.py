"""Router modules for Mock Backends service."""

from src.routers.health import router as health_router
from src.routers.fraud import router as fraud_router
from src.routers.settlement import router as settlement_router
from src.routers.sanctions import router as sanctions_router
from src.routers.demo import router as demo_router

__all__ = [
    "health_router",
    "fraud_router",
    "settlement_router",
    "sanctions_router",
    "demo_router",
]
