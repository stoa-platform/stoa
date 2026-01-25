-- =============================================================================
-- STOA Platform - Database Initialization
-- =============================================================================
-- This script runs automatically when PostgreSQL container starts for the
-- first time. It creates required extensions for the STOA Platform.
-- =============================================================================

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trigram-based text search (for API catalog search)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Ensure the stoa user has full privileges
GRANT ALL PRIVILEGES ON DATABASE stoa_platform TO stoa;
