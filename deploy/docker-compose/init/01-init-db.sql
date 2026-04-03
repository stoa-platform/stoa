-- =============================================================================
-- STOA Platform - Database Initialization
-- =============================================================================
-- This script runs automatically when PostgreSQL container starts for the
-- first time. It creates required databases and extensions.
-- =============================================================================

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trigram-based text search (for API catalog search)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Ensure the stoa user has full privileges on the main database
GRANT ALL PRIVILEGES ON DATABASE stoa_platform TO stoa;

-- Dedicated Keycloak database (CAB-1955)
-- Same PostgreSQL instance, separate database for isolation
CREATE DATABASE keycloak OWNER stoa;
GRANT ALL PRIVILEGES ON DATABASE keycloak TO stoa;
