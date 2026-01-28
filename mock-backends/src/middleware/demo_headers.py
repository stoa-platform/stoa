"""Demo headers middleware - adds X-Demo-Mode and X-Data-Classification headers.

CAB-1018: Mock APIs for Central Bank Demo
Council feedback (Team Coca): Clear identification of mock data.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.config import settings


class DemoHeadersMiddleware(BaseHTTPMiddleware):
    """Add demo identification headers to all responses.

    Headers added:
    - X-Demo-Mode: true/false - Indicates this is a demo/mock service
    - X-Data-Classification: SYNTHETIC - Data type classification
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Add demo identification headers (Council requirement)
        if settings.demo_mode:
            response.headers["X-Demo-Mode"] = "true"
            response.headers["X-Data-Classification"] = "SYNTHETIC"
        else:
            response.headers["X-Demo-Mode"] = "false"

        return response
