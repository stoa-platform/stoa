# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Mock sanctions database for Sanctions Screening API.

CAB-1018: Mock APIs for Central Bank Demo
Simulated sanctions lists with ~20 entries each.

All data is 100% synthetic - generated with Faker seed 42.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from faker import Faker

from src.config import settings
from src.logging_config import get_logger
from src.schemas.sanctions import EntityType, SanctionMatch
from src.services.semantic_cache import normalize

logger = get_logger(__name__)

# Initialize Faker with fixed seed
fake = Faker()
Faker.seed(settings.faker_seed)


@dataclass
class SanctionEntry:
    """Entry in a sanctions list."""

    entry_id: str
    name: str
    entity_type: EntityType
    country: str
    listed_date: str
    reason: str
    aliases: list[str]


@dataclass
class SanctionsList:
    """A sanctions list with entries."""

    name: str
    version: str
    last_updated: str
    entries: list[SanctionEntry]


# ========== Mock Sanctions Data ==========

OFAC_ENTRIES = [
    SanctionEntry(
        entry_id="OFAC-2024-001",
        name="Ivan Petrov",
        entity_type=EntityType.PERSON,
        country="RU",
        listed_date="2024-03-15",
        reason="Sanctions evasion activities",
        aliases=["I. Petrov", "Ivan P."],
    ),
    SanctionEntry(
        entry_id="OFAC-2024-002",
        name="Omega Trading Corp",
        entity_type=EntityType.ORGANIZATION,
        country="IR",
        listed_date="2024-02-20",
        reason="Proliferation financing",
        aliases=["Omega Corp", "OTC Holdings"],
    ),
    SanctionEntry(
        entry_id="OFAC-2024-003",
        name="Alexei Sokolov",
        entity_type=EntityType.PERSON,
        country="RU",
        listed_date="2024-01-10",
        reason="Energy sector sanctions",
        aliases=["A. Sokolov"],
    ),
    SanctionEntry(
        entry_id="OFAC-2024-004",
        name="Tehran Industrial Group",
        entity_type=EntityType.ORGANIZATION,
        country="IR",
        listed_date="2023-11-05",
        reason="Nuclear program support",
        aliases=["TIG", "Tehran Industries"],
    ),
    SanctionEntry(
        entry_id="OFAC-2024-005",
        name="Dmitri Volkov",
        entity_type=EntityType.PERSON,
        country="RU",
        listed_date="2023-09-15",
        reason="Defense sector involvement",
        aliases=["D. Volkov", "Dmitry Volkov"],
    ),
    SanctionEntry(
        entry_id="OFAC-2024-006",
        name="Persian Gulf Shipping",
        entity_type=EntityType.ORGANIZATION,
        country="IR",
        listed_date="2023-08-01",
        reason="Sanctions circumvention",
        aliases=["PGS", "Gulf Shipping Co"],
    ),
    SanctionEntry(
        entry_id="OFAC-2024-007",
        name="Sergei Morozov",
        entity_type=EntityType.PERSON,
        country="RU",
        listed_date="2023-06-20",
        reason="Financial sector sanctions",
        aliases=["S. Morozov"],
    ),
    SanctionEntry(
        entry_id="OFAC-2024-008",
        name="Caspian Energy Ltd",
        entity_type=EntityType.ORGANIZATION,
        country="RU",
        listed_date="2023-05-10",
        reason="Energy sector sanctions",
        aliases=["Caspian Energy", "CEL"],
    ),
]

EU_SANCTIONS_ENTRIES = [
    SanctionEntry(
        entry_id="EU-2024-001",
        name="Viktor Volkov",
        entity_type=EntityType.PERSON,
        country="BY",
        listed_date="2024-04-01",
        reason="Human rights violations",
        aliases=["V. Volkov"],
    ),
    SanctionEntry(
        entry_id="EU-2024-002",
        name="Northern Energy LLC",
        entity_type=EntityType.ORGANIZATION,
        country="RU",
        listed_date="2024-03-10",
        reason="Energy sector restrictions",
        aliases=["Northern Energy", "NE LLC"],
    ),
    SanctionEntry(
        entry_id="EU-2024-003",
        name="Andrei Kuznetsov",
        entity_type=EntityType.PERSON,
        country="RU",
        listed_date="2024-02-15",
        reason="Defense sector involvement",
        aliases=["A. Kuznetsov"],
    ),
    SanctionEntry(
        entry_id="EU-2024-004",
        name="Minsk Industrial Complex",
        entity_type=EntityType.ORGANIZATION,
        country="BY",
        listed_date="2024-01-20",
        reason="State-owned enterprise restrictions",
        aliases=["MIC", "Minsk Industries"],
    ),
    SanctionEntry(
        entry_id="EU-2024-005",
        name="Pavel Sidorov",
        entity_type=EntityType.PERSON,
        country="BY",
        listed_date="2023-12-05",
        reason="Election interference",
        aliases=["P. Sidorov"],
    ),
    SanctionEntry(
        entry_id="EU-2024-006",
        name="Baltic Freight Services",
        entity_type=EntityType.ORGANIZATION,
        country="RU",
        listed_date="2023-10-15",
        reason="Sanctions circumvention",
        aliases=["BFS", "Baltic Freight"],
    ),
    SanctionEntry(
        entry_id="EU-2024-007",
        name="Nikolai Petrov",
        entity_type=EntityType.PERSON,
        country="RU",
        listed_date="2023-09-01",
        reason="Oligarch designation",
        aliases=["N. Petrov"],
    ),
]

UN_CONSOLIDATED_ENTRIES = [
    SanctionEntry(
        entry_id="UN-2024-001",
        name="Ahmed Hassan",
        entity_type=EntityType.PERSON,
        country="SY",
        listed_date="2024-03-25",
        reason="Chemical weapons program",
        aliases=["A. Hassan"],
    ),
    SanctionEntry(
        entry_id="UN-2024-002",
        name="Global Shipping Ltd",
        entity_type=EntityType.ORGANIZATION,
        country="KP",
        listed_date="2024-02-28",
        reason="WMD proliferation",
        aliases=["Global Shipping", "GSL"],
    ),
    SanctionEntry(
        entry_id="UN-2024-003",
        name="Kim Jong-sik",
        entity_type=EntityType.PERSON,
        country="KP",
        listed_date="2024-01-15",
        reason="Missile program involvement",
        aliases=["Jong-sik Kim"],
    ),
    SanctionEntry(
        entry_id="UN-2024-004",
        name="Damascus Trading Company",
        entity_type=EntityType.ORGANIZATION,
        country="SY",
        listed_date="2023-11-20",
        reason="Support for Syrian regime",
        aliases=["DTC", "Damascus Trading"],
    ),
    SanctionEntry(
        entry_id="UN-2024-005",
        name="Mohammed Al-Rashid",
        entity_type=EntityType.PERSON,
        country="SY",
        listed_date="2023-10-05",
        reason="Terrorism financing",
        aliases=["M. Al-Rashid", "Al-Rashid"],
    ),
    SanctionEntry(
        entry_id="UN-2024-006",
        name="Pyongyang Tech Industries",
        entity_type=EntityType.ORGANIZATION,
        country="KP",
        listed_date="2023-08-15",
        reason="Nuclear program support",
        aliases=["PTI", "Pyongyang Tech"],
    ),
]


class SanctionsDatabase:
    """Mock sanctions database with search capabilities.

    Contains three simulated lists:
    - OFAC (US Treasury)
    - EU_SANCTIONS (European Union)
    - UN_CONSOLIDATED (United Nations)

    Matching algorithm:
    - Exact normalized match = 100% score
    - Partial match (contains) = 60-80% score
    - Alias match = 90% score
    """

    def __init__(self):
        self._lists = {
            "OFAC": SanctionsList(
                name="OFAC",
                version="2026.01.15",
                last_updated="2026-01-15T00:00:00Z",
                entries=OFAC_ENTRIES,
            ),
            "EU_SANCTIONS": SanctionsList(
                name="EU_SANCTIONS",
                version="2026.01.10",
                last_updated="2026-01-10T00:00:00Z",
                entries=EU_SANCTIONS_ENTRIES,
            ),
            "UN_CONSOLIDATED": SanctionsList(
                name="UN_CONSOLIDATED",
                version="2026.01.05",
                last_updated="2026-01-05T00:00:00Z",
                entries=UN_CONSOLIDATED_ENTRIES,
            ),
        }

    def search(
        self,
        entity_name: str,
        entity_type: EntityType,
        country: Optional[str] = None,
    ) -> list[SanctionMatch]:
        """Search for entity across all sanctions lists.

        Args:
            entity_name: Name to search for
            entity_type: Type of entity
            country: Optional country filter

        Returns:
            List of matches with scores
        """
        matches: list[SanctionMatch] = []
        normalized_query = normalize(entity_name)

        for list_name, sanctions_list in self._lists.items():
            for entry in sanctions_list.entries:
                # Filter by entity type
                if entry.entity_type != entity_type:
                    continue

                # Calculate match score
                score = self._calculate_match_score(
                    normalized_query, entry, country
                )

                if score >= 60:  # Minimum threshold for partial match
                    matches.append(
                        SanctionMatch(
                            list_name=list_name,
                            entry_name=entry.name,
                            match_score=score,
                            entry_id=entry.entry_id,
                            listed_date=entry.listed_date,
                            reason=entry.reason,
                        )
                    )

        # Sort by score descending
        matches.sort(key=lambda m: m.match_score, reverse=True)

        logger.info(
            "Sanctions search completed",
            entity_name=entity_name,
            normalized=normalized_query,
            matches_found=len(matches),
        )

        return matches

    def _calculate_match_score(
        self,
        normalized_query: str,
        entry: SanctionEntry,
        country: Optional[str],
    ) -> int:
        """Calculate match score between query and entry.

        Scoring:
        - Exact match (normalized) = 100
        - Alias exact match = 90
        - Query contains entry name = 75
        - Entry name contains query = 70
        - Country mismatch penalty = -10

        Args:
            normalized_query: Normalized search query
            entry: Sanctions entry to compare
            country: Country filter (optional)

        Returns:
            Match score (0-100)
        """
        normalized_entry = normalize(entry.name)
        score = 0

        # Exact match
        if normalized_query == normalized_entry:
            score = 100
        else:
            # Check aliases
            for alias in entry.aliases:
                if normalized_query == normalize(alias):
                    score = 90
                    break

            # Partial matches
            if score == 0:
                if normalized_entry in normalized_query:
                    score = 75
                elif normalized_query in normalized_entry:
                    score = 70
                elif self._word_overlap(normalized_query, normalized_entry) >= 0.5:
                    score = 65

        # Country bonus/penalty
        if country and score > 0:
            if entry.country.upper() == country.upper():
                score = min(100, score + 5)  # Country match bonus
            else:
                score = max(0, score - 10)  # Country mismatch penalty

        return score

    def _word_overlap(self, query: str, entry: str) -> float:
        """Calculate word overlap ratio.

        Args:
            query: Query string
            entry: Entry string

        Returns:
            Overlap ratio (0.0-1.0)
        """
        query_words = set(query.split())
        entry_words = set(entry.split())

        if not query_words or not entry_words:
            return 0.0

        overlap = len(query_words & entry_words)
        return overlap / max(len(query_words), len(entry_words))

    def get_list_versions(self) -> list[dict]:
        """Get version information for all lists.

        Returns:
            List of version info dicts
        """
        return [
            {
                "name": sanctions_list.name,
                "version": sanctions_list.version,
                "last_updated": sanctions_list.last_updated,
                "entry_count": len(sanctions_list.entries),
            }
            for sanctions_list in self._lists.values()
        ]

    def get_list_names(self) -> list[str]:
        """Get names of all sanctions lists.

        Returns:
            List of list names
        """
        return list(self._lists.keys())


# Singleton instance
_sanctions_database: Optional[SanctionsDatabase] = None


def get_sanctions_database() -> SanctionsDatabase:
    """Get the singleton sanctions database instance."""
    global _sanctions_database
    if _sanctions_database is None:
        _sanctions_database = SanctionsDatabase()
    return _sanctions_database
