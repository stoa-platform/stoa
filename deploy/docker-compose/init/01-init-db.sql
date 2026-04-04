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

-- Vault dynamic credentials admin role (Phase 4)
-- Vault Database engine uses this role to create/revoke ephemeral credentials.
-- CREATEROLE allows Vault to CREATE ROLE for dynamic users.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'vault_admin') THEN
    CREATE ROLE vault_admin WITH LOGIN PASSWORD 'vault-admin-local' CREATEROLE SUPERUSER;
    GRANT ALL PRIVILEGES ON DATABASE stoa_platform TO vault_admin;
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO vault_admin;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO vault_admin;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO vault_admin;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO vault_admin;
  END IF;
END
$$;
