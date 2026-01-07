"""Middleware package for Control-Plane API."""

from .metrics import MetricsMiddleware

__all__ = ["MetricsMiddleware"]
