-- =============================================================================
-- STOA Platform - PostgreSQL Triggers for OpenSearch Sync
-- =============================================================================
-- Creates triggers to notify the sync service of tool changes
--
-- Run with: psql -U stoa -d stoa -f sync_triggers.sql
-- =============================================================================

-- Create table to track deletions (for incremental sync)
CREATE TABLE IF NOT EXISTS tool_deletions (
    id SERIAL PRIMARY KEY,
    tool_id UUID NOT NULL,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by UUID,
    tenant_id UUID
);

CREATE INDEX IF NOT EXISTS idx_tool_deletions_deleted_at 
ON tool_deletions(deleted_at);

-- Cleanup old deletion records (keep 30 days)
CREATE OR REPLACE FUNCTION cleanup_old_deletions()
RETURNS void AS $$
BEGIN
    DELETE FROM tool_deletions 
    WHERE deleted_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Function to notify changes
CREATE OR REPLACE FUNCTION notify_tool_change()
RETURNS TRIGGER AS $$
DECLARE
    payload JSON;
    operation TEXT;
    tool_id TEXT;
BEGIN
    operation := TG_OP;
    
    IF (TG_OP = 'DELETE') THEN
        tool_id := OLD.id::TEXT;
        
        -- Record deletion for incremental sync
        INSERT INTO tool_deletions (tool_id, tenant_id)
        VALUES (OLD.id, OLD.tenant_id);
        
        payload := json_build_object(
            'operation', operation,
            'id', tool_id,
            'tenant_id', OLD.tenant_id::TEXT,
            'timestamp', NOW()
        );
    ELSE
        tool_id := NEW.id::TEXT;
        payload := json_build_object(
            'operation', operation,
            'id', tool_id,
            'tenant_id', NEW.tenant_id::TEXT,
            'name', NEW.name,
            'timestamp', NOW()
        );
    END IF;
    
    -- Send notification
    PERFORM pg_notify('tool_changes', payload::TEXT);
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Drop existing trigger if exists
DROP TRIGGER IF EXISTS tool_change_trigger ON tools;

-- Create trigger for INSERT, UPDATE, DELETE
CREATE TRIGGER tool_change_trigger
AFTER INSERT OR UPDATE OR DELETE ON tools
FOR EACH ROW
EXECUTE FUNCTION notify_tool_change();

-- Function to notify stats updates
CREATE OR REPLACE FUNCTION notify_tool_stats_change()
RETURNS TRIGGER AS $$
DECLARE
    payload JSON;
BEGIN
    payload := json_build_object(
        'operation', 'STATS_UPDATE',
        'id', NEW.tool_id::TEXT,
        'call_count', NEW.call_count,
        'avg_latency_ms', NEW.avg_latency_ms,
        'success_rate', NEW.success_rate,
        'timestamp', NOW()
    );
    
    PERFORM pg_notify('tool_changes', payload::TEXT);
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Drop existing stats trigger if exists
DROP TRIGGER IF EXISTS tool_stats_change_trigger ON tool_stats;

-- Create trigger for stats updates
CREATE TRIGGER tool_stats_change_trigger
AFTER INSERT OR UPDATE ON tool_stats
FOR EACH ROW
EXECUTE FUNCTION notify_tool_stats_change();

-- Grant permissions
GRANT SELECT ON tool_deletions TO stoa;

-- Create scheduled job to cleanup deletions (if pg_cron is available)
-- SELECT cron.schedule('cleanup-tool-deletions', '0 3 * * *', 'SELECT cleanup_old_deletions()');

-- Verify triggers
DO $$
BEGIN
    RAISE NOTICE 'Triggers created successfully!';
    RAISE NOTICE 'Listening on channel: tool_changes';
END $$;
