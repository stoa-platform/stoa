"""CAB-660: Seed demo data (Ready Player One theme).

Revision ID: 002_cab660
Revises: 001_cab660
Create Date: 2026-01-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_cab660"
down_revision: Union[str, None] = "001_cab660"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants
    op.execute("""
        INSERT INTO tenants (id, name, description, status, settings) VALUES
            ('oasis-gunters', 'OASIS Gunters', 'Independent egg hunters seeking Halliday''s Easter Egg', 'active',
             '{"max_apis": 10, "max_subscriptions": 50, "rate_limit_rpm": 1000}'),
            ('ioi-sixers', 'IOI Sixers Division', 'Innovative Online Industries - Corporate egg hunting division', 'active',
             '{"max_apis": 50, "max_subscriptions": 500, "rate_limit_rpm": 10000}'),
            ('gregarious-games', 'Gregarious Games', 'Creators of the OASIS - Halliday & Morrow''s legacy', 'active',
             '{"max_apis": -1, "max_subscriptions": -1, "rate_limit_rpm": -1}'),
            ('og-atari', 'OG Atari Archives', 'Legacy gaming APIs - archived', 'archived',
             '{}')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            status = EXCLUDED.status;
    """)

    # Users
    op.execute("""
        INSERT INTO users (id, keycloak_id, email, name, tenant_id, roles, avatar) VALUES
            ('parzival', 'parzival', 'wade.watts@gunters.oasis', 'Parzival (Wade Watts)', 'oasis-gunters',
             ARRAY['api-developer', 'subscriber'], '🎮'),
            ('art3mis', 'art3mis', 'samantha.cook@gunters.oasis', 'Art3mis (Samantha Cook)', 'oasis-gunters',
             ARRAY['api-developer', 'subscriber'], '🦋'),
            ('aech', 'aech', 'helen.harris@gunters.oasis', 'Aech (Helen Harris)', 'oasis-gunters',
             ARRAY['api-developer', 'subscriber'], '🔧'),
            ('sorrento', 'sorrento', 'nolan.sorrento@ioi.corp', 'Nolan Sorrento', 'ioi-sixers',
             ARRAY['tenant-admin', 'subscriber'], '💼'),
            ('sixer-42', 'sixer-42', 'operative.42@ioi.corp', 'Sixer #42', 'ioi-sixers',
             ARRAY['subscriber'], '🤖'),
            ('halliday', 'halliday', 'james.halliday@gregarious.games', 'James Halliday (Anorak)', 'gregarious-games',
             ARRAY['platform-admin'], '🧙'),
            ('morrow', 'morrow', 'ogden.morrow@gregarious.games', 'Ogden Morrow (Og)', 'gregarious-games',
             ARRAY['platform-admin'], '👴')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            tenant_id = EXCLUDED.tenant_id,
            roles = EXCLUDED.roles;
    """)

    # Quest APIs (Gregarious Games)
    op.execute("""
        INSERT INTO apis (id, name, description, category, status, version, owner_tenant_id, access_type, allowed_tenants, tags, rate_limit) VALUES
            ('copper-key-api', 'Copper Key API', 'The first key. Where it all begins. Complete the Joust challenge.',
             'Quest', 'active', '1.0.0', 'gregarious-games', 'public', '{}',
             ARRAY['quest', 'key', 'challenge', 'joust'], '100/hour'),

            ('jade-key-api', 'Jade Key API', 'Unlock the Jade Gate. Requires completing the Zork quest.',
             'Quest', 'active', '1.0.0', 'gregarious-games', 'restricted', ARRAY['oasis-gunters'],
             ARRAY['quest', 'key', 'challenge', 'zork'], '50/hour'),

            ('crystal-key-api', 'Crystal Key API', 'The final key. Only for those who proved worthy.',
             'Quest', 'active', '1.0.0', 'gregarious-games', 'restricted', '{}',
             ARRAY['quest', 'key', 'final', 'adventure'], '10/hour'),

            ('easter-egg-api', 'Easter Egg API', 'The ultimate prize. Access granted only to the worthy.',
             'Secret', 'active', '???', 'gregarious-games', 'restricted', '{}',
             ARRAY['easter-egg', 'final', 'prize'], '1/lifetime')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            access_type = EXCLUDED.access_type,
            allowed_tenants = EXCLUDED.allowed_tenants;
    """)

    # Gunter Tools (OASIS Gunters)
    op.execute("""
        INSERT INTO apis (id, name, description, category, status, version, owner_tenant_id, access_type, tags, rate_limit) VALUES
            ('quest-api', 'OASIS Quest API', 'Track and manage your quest progress across the OASIS.',
             'Gunter Tools', 'active', '2.1.0', 'oasis-gunters', 'tenant',
             ARRAY['quest', 'progress', 'tracking'], '500/hour'),

            ('artifact-api', 'Artifact Collection API', 'Manage your collection of OASIS artifacts and items.',
             'Gunter Tools', 'active', '1.5.0', 'oasis-gunters', 'tenant',
             ARRAY['inventory', 'artifacts', 'items'], '200/hour')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description;
    """)

    # IOI Corporate APIs
    op.execute("""
        INSERT INTO apis (id, name, description, category, status, version, owner_tenant_id, access_type, tags, rate_limit) VALUES
            ('loyalty-api', 'IOI Loyalty Program API', 'Track employee... er, contractor loyalty metrics.',
             'Corporate', 'active', '3.0.0', 'ioi-sixers', 'tenant',
             ARRAY['hr', 'loyalty', 'tracking', 'corporate'], '1000/hour'),

            ('sixers-army-api', 'Sixers Army Management API', 'Coordinate Sixer operatives in the OASIS.',
             'Corporate', 'active', '2.0.0', 'ioi-sixers', 'tenant',
             ARRAY['military', 'coordination', 'operatives'], '500/hour'),

            ('surveillance-api', 'OASIS Surveillance API', 'Monitor gunter activities across the OASIS. Totally legal.',
             'Corporate', 'active', '1.0.0', 'ioi-sixers', 'tenant',
             ARRAY['surveillance', 'monitoring', 'tracking'], '100/hour')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description;
    """)

    # Lore APIs (Gregarious Games - Public)
    op.execute("""
        INSERT INTO apis (id, name, description, category, status, version, owner_tenant_id, access_type, tags, rate_limit) VALUES
            ('halliday-journal-api', 'Halliday''s Journal API', 'Anorak''s Almanac - Official hints and lore for the Easter Egg hunt.',
             'Lore', 'active', '1.0.0', 'gregarious-games', 'public',
             ARRAY['lore', 'hints', 'halliday', 'almanac'], '1000/hour')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description;
    """)

    # API Endpoints
    op.execute("""
        INSERT INTO api_endpoints (api_id, method, path, description) VALUES
            ('jade-key-api', 'GET', '/hints', 'Get hints for finding the Jade Key'),
            ('jade-key-api', 'POST', '/attempt', 'Attempt to claim the Jade Key'),
            ('jade-key-api', 'GET', '/status', 'Check your progress toward the Jade Key'),
            ('copper-key-api', 'GET', '/hints', 'Get hints for the Copper Key'),
            ('copper-key-api', 'POST', '/challenge/start', 'Start the Joust challenge'),
            ('copper-key-api', 'POST', '/challenge/submit', 'Submit your challenge attempt'),
            ('copper-key-api', 'GET', '/leaderboard', 'View the challenge leaderboard'),
            ('loyalty-api', 'GET', '/score/{employee_id}', 'Get loyalty score for an employee'),
            ('loyalty-api', 'POST', '/report', 'Report disloyalty incident'),
            ('loyalty-api', 'GET', '/leaderboard', 'Top loyal employees'),
            ('halliday-journal-api', 'GET', '/entries', 'List all journal entries'),
            ('halliday-journal-api', 'GET', '/entries/{date}', 'Get entry by date'),
            ('halliday-journal-api', 'GET', '/search', 'Search the journal')
        ON CONFLICT (api_id, method, path) DO NOTHING;
    """)

    # Subscriptions (using mcp_subscriptions table to avoid conflict)
    op.execute("""
        INSERT INTO mcp_subscriptions (id, user_id, tenant_id, api_id, plan, status, created_at) VALUES
            ('sub-parzival-copper-001', 'parzival', 'oasis-gunters', 'copper-key-api', 'gunter', 'active', '2025-11-01'),
            ('sub-parzival-jade-001', 'parzival', 'oasis-gunters', 'jade-key-api', 'gunter', 'active', '2026-01-15'),
            ('sub-parzival-journal-001', 'parzival', 'oasis-gunters', 'halliday-journal-api', 'free', 'active', '2025-06-01'),
            ('sub-art3mis-copper-001', 'art3mis', 'oasis-gunters', 'copper-key-api', 'gunter', 'active', '2025-10-15'),
            ('sub-sorrento-loyalty-001', 'sorrento', 'ioi-sixers', 'loyalty-api', 'enterprise', 'active', '2025-01-01'),
            ('sub-sorrento-surveillance-001', 'sorrento', 'ioi-sixers', 'surveillance-api', 'enterprise', 'active', '2025-01-01'),
            ('sub-sixer42-jade-denied', 'sixer-42', 'ioi-sixers', 'jade-key-api', 'enterprise', 'denied',
             '2026-01-18 14:23:00')
        ON CONFLICT (id) DO NOTHING;
    """)

    # Update the denied subscription with reason
    op.execute("""
        UPDATE mcp_subscriptions
        SET denial_reason = 'API restricted to oasis-gunters tenant'
        WHERE id = 'sub-sixer42-jade-denied';
    """)

    # Audit Logs
    op.execute("""
        INSERT INTO audit_logs (timestamp, user_id, tenant_id, action, resource_type, resource_id, status, details, ip_address) VALUES
            ('2026-01-18 14:23:00+00', 'sixer-42', 'ioi-sixers', 'subscription.create', 'api', 'jade-key-api', 'denied',
             '{"reason": "API restricted to oasis-gunters tenant"}', '10.0.42.101'),
            ('2026-01-18 14:25:00+00', 'sixer-42', 'ioi-sixers', 'subscription.create', 'api', 'jade-key-api', 'denied',
             '{"reason": "API restricted to oasis-gunters tenant"}', '10.0.42.101'),
            ('2026-01-18 14:26:00+00', 'sixer-42', 'ioi-sixers', 'subscription.create', 'api', 'jade-key-api', 'denied',
             '{"reason": "API restricted to oasis-gunters tenant", "attempt": 3}', '10.0.42.101'),
            ('2026-01-18 15:01:00+00', 'sorrento', 'ioi-sixers', 'subscription.rotate_key', 'subscription', 'sub-sorrento-loyalty-001', 'success',
             '{"grace_period_hours": 24}', '10.0.1.1'),
            ('2026-01-18 16:01:00+00', 'parzival', 'oasis-gunters', 'api.call', 'api', 'jade-key-api', 'success',
             '{"endpoint": "GET /hints", "response_code": 200}', '192.168.1.42'),
            ('2026-01-18 16:05:00+00', 'parzival', 'oasis-gunters', 'api.call', 'api', 'jade-key-api', 'success',
             '{"endpoint": "POST /attempt", "response_code": 200}', '192.168.1.42'),
            ('2026-01-18 16:06:00+00', 'parzival', 'oasis-gunters', 'api.call', 'api', 'jade-key-api', 'success',
             '{"endpoint": "POST /attempt", "response_code": 201, "note": "JADE KEY FOUND!"}', '192.168.1.42');
    """)

    # UAC Contracts
    op.execute("""
        INSERT INTO uac_contracts (id, name, description, status, terms, tenant_ids, api_ids) VALUES
            ('uac-enterprise-sla', 'Enterprise SLA', 'Standard enterprise service level agreement', 'active',
             '{"uptime": "99.9%", "latency_p99_max": "500ms", "error_rate_max": "0.1%", "support_response": "4h"}',
             ARRAY['ioi-sixers', 'gregarious-games'], '{}'),
            ('uac-gunter-free', 'Gunter Free Tier', 'Best-effort service for independent egg hunters', 'active',
             '{"uptime": "99%", "latency_p99_max": "2000ms", "rate_limit": "1000/day"}',
             ARRAY['oasis-gunters'], '{}')
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            terms = EXCLUDED.terms;
    """)


def downgrade() -> None:
    # Delete in reverse order to avoid FK constraints
    op.execute("DELETE FROM uac_contracts WHERE id IN ('uac-enterprise-sla', 'uac-gunter-free');")
    op.execute("DELETE FROM audit_logs WHERE user_id IN ('sixer-42', 'sorrento', 'parzival');")
    op.execute("DELETE FROM mcp_subscriptions WHERE id LIKE 'sub-%';")
    op.execute("DELETE FROM api_endpoints WHERE api_id IN ('jade-key-api', 'copper-key-api', 'loyalty-api', 'halliday-journal-api');")
    op.execute("DELETE FROM apis WHERE id IN ('copper-key-api', 'jade-key-api', 'crystal-key-api', 'easter-egg-api', 'quest-api', 'artifact-api', 'loyalty-api', 'sixers-army-api', 'surveillance-api', 'halliday-journal-api');")
    op.execute("DELETE FROM users WHERE id IN ('parzival', 'art3mis', 'aech', 'sorrento', 'sixer-42', 'halliday', 'morrow');")
    op.execute("DELETE FROM tenants WHERE id IN ('oasis-gunters', 'ioi-sixers', 'gregarious-games', 'og-atari');")
