"""Sanctions Screening API schemas.

CAB-1018: Mock APIs for Central Bank Demo
Pydantic models for entity sanctions screening with semantic cache.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Type of entity being screened."""

    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"


class ScreeningResult(str, Enum):
    """Result of sanctions screening."""

    HIT = "HIT"  # High confidence match (score >= 90)
    PARTIAL_MATCH = "PARTIAL_MATCH"  # Medium confidence (60-89)
    NO_HIT = "NO_HIT"  # No match (score < 60)


class SanctionMatch(BaseModel):
    """A match found in sanctions lists."""

    list_name: str = Field(description="Name of the sanctions list")
    entry_name: str = Field(description="Name as it appears in the list")
    match_score: int = Field(
        ge=0, le=100, description="Match confidence score (0-100)"
    )
    entry_id: str = Field(description="Unique identifier in the list")
    listed_date: str = Field(description="Date when entity was listed")
    reason: str = Field(description="Reason for listing")

    model_config = {
        "json_schema_extra": {
            "example": {
                "list_name": "OFAC",
                "entry_name": "Ivan Petrov",
                "match_score": 100,
                "entry_id": "OFAC-2024-001",
                "listed_date": "2024-03-15",
                "reason": "Sanctions evasion activities",
            }
        }
    }


class ScreeningRequest(BaseModel):
    """Request model for sanctions screening."""

    entity_name: str = Field(
        ...,
        min_length=2,
        description="Name of entity to screen",
        examples=["Ivan Petrov", "Omega Trading Corp"],
    )
    entity_type: EntityType = Field(
        ...,
        description="Type of entity",
        examples=[EntityType.PERSON, EntityType.ORGANIZATION],
    )
    country: str = Field(
        ...,
        min_length=2,
        max_length=3,
        description="ISO country code (2 or 3 letter)",
        examples=["RU", "IR", "US"],
    )
    additional_info: Optional[dict] = Field(
        default=None,
        description="Additional information for screening",
        examples=[{"date_of_birth": "1970-01-01", "nationality": "Russian"}],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "entity_name": "Ivan Petrov",
                "entity_type": "PERSON",
                "country": "RU",
                "additional_info": {"nationality": "Russian"},
            }
        }
    }


class ScreeningResponse(BaseModel):
    """Response model for sanctions screening."""

    result: ScreeningResult = Field(description="Screening result")
    matches: list[SanctionMatch] = Field(
        default_factory=list, description="List of matches found"
    )
    confidence: int = Field(
        ge=0, le=100, description="Overall confidence score"
    )
    list_sources: list[str] = Field(
        description="Sanctions lists checked"
    )
    entity_name: str = Field(description="Entity name as provided")
    entity_name_normalized: str = Field(description="Normalized entity name")
    entity_type: EntityType = Field(description="Entity type")
    country: str = Field(description="Country code")
    cached: bool = Field(
        default=False, description="Whether result was from cache"
    )
    processing_time_ms: int = Field(description="Processing time in milliseconds")
    timestamp: str = Field(description="ISO timestamp of screening")

    model_config = {
        "json_schema_extra": {
            "example": {
                "result": "HIT",
                "matches": [
                    {
                        "list_name": "OFAC",
                        "entry_name": "Ivan Petrov",
                        "match_score": 100,
                        "entry_id": "OFAC-2024-001",
                        "listed_date": "2024-03-15",
                        "reason": "Sanctions evasion activities",
                    }
                ],
                "confidence": 100,
                "list_sources": ["OFAC", "EU_SANCTIONS", "UN_CONSOLIDATED"],
                "entity_name": "Ivan Petrov",
                "entity_name_normalized": "ivan petrov",
                "entity_type": "PERSON",
                "country": "RU",
                "cached": False,
                "processing_time_ms": 45,
                "timestamp": "2026-02-26T10:00:00Z",
            }
        }
    }


class ListInfo(BaseModel):
    """Information about a sanctions list."""

    name: str = Field(description="List name")
    version: str = Field(description="List version")
    last_updated: str = Field(description="Last update date")
    entry_count: int = Field(description="Number of entries in list")


class ListVersionResponse(BaseModel):
    """Response model for list versions."""

    lists: list[ListInfo] = Field(description="Information about all sanctions lists")
    timestamp: str = Field(description="ISO timestamp")

    model_config = {
        "json_schema_extra": {
            "example": {
                "lists": [
                    {
                        "name": "OFAC",
                        "version": "2026.01.15",
                        "last_updated": "2026-01-15T00:00:00Z",
                        "entry_count": 8,
                    },
                    {
                        "name": "EU_SANCTIONS",
                        "version": "2026.01.10",
                        "last_updated": "2026-01-10T00:00:00Z",
                        "entry_count": 7,
                    },
                    {
                        "name": "UN_CONSOLIDATED",
                        "version": "2026.01.05",
                        "last_updated": "2026-01-05T00:00:00Z",
                        "entry_count": 6,
                    },
                ],
                "timestamp": "2026-02-26T10:00:00Z",
            }
        }
    }
