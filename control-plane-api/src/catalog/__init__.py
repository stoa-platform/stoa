"""Curated EU Public API Catalog — YAML-driven registry (CAB-1639)."""

from src.catalog.loader import get_catalog, get_categories, reload_catalog

__all__ = ["get_catalog", "get_categories", "reload_catalog"]
