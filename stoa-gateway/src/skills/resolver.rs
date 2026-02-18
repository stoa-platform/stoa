//! Skill Resolver — CSS cascade context injection (CAB-1314)
//!
//! Stores skills from K8s CRDs and resolves them using specificity ordering.
//! Uses `parking_lot::RwLock` (sync, non-poisoning) for the skill store and
//! `moka::sync::Cache` for resolved-set caching.

use std::fmt;
use std::sync::Arc;

use moka::sync::Cache;
use parking_lot::RwLock;

/// Skill scope — determines specificity in the CSS cascade model.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SkillScope {
    /// Applies to all tenants (specificity 0)
    Global,
    /// Applies to a specific tenant (specificity 1)
    Tenant,
    /// Applies to a specific tool within a tenant (specificity 2)
    Tool,
    /// Applies to a specific user within a tenant (specificity 3)
    User,
}

impl SkillScope {
    /// CSS-like specificity value. Higher = more specific = wins cascade.
    pub fn specificity(self) -> u8 {
        match self {
            Self::Global => 0,
            Self::Tenant => 1,
            Self::Tool => 2,
            Self::User => 3,
        }
    }

    /// Parse from CRD string value.
    pub fn from_crd(s: &str) -> Option<Self> {
        match s {
            "global" => Some(Self::Global),
            "tenant" => Some(Self::Tenant),
            "tool" => Some(Self::Tool),
            "user" => Some(Self::User),
            _ => None,
        }
    }
}

impl fmt::Display for SkillScope {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Global => write!(f, "global"),
            Self::Tenant => write!(f, "tenant"),
            Self::Tool => write!(f, "tool"),
            Self::User => write!(f, "user"),
        }
    }
}

/// A skill stored in the resolver (populated from K8s CRD events).
#[derive(Debug, Clone)]
pub struct StoredSkill {
    /// Unique key: `{namespace}/{name}` from K8s metadata
    pub key: String,
    /// Human-readable name
    pub name: String,
    /// Optional description
    pub description: Option<String>,
    /// Tenant ID (from K8s namespace)
    pub tenant_id: String,
    /// CSS cascade scope
    pub scope: SkillScope,
    /// Priority within the same scope (0-100, higher wins)
    pub priority: u8,
    /// System prompt instructions injected into agent context
    pub instructions: Option<String>,
    /// Tool reference (for scope=tool)
    pub tool_ref: Option<String>,
    /// User reference (for scope=user)
    pub user_ref: Option<String>,
    /// Whether this skill is active
    pub enabled: bool,
}

/// A skill after CSS cascade resolution.
#[derive(Debug, Clone)]
pub struct ResolvedSkill {
    pub name: String,
    pub scope: SkillScope,
    pub priority: u8,
    pub instructions: Option<String>,
    pub specificity: u8,
}

/// Skill resolver with in-memory store and TTL cache for resolved sets.
///
/// Uses `parking_lot::RwLock` because all operations are purely in-memory
/// (no `.await` while holding the lock). `moka::sync::Cache` provides
/// TTL-based eviction for resolved skill sets.
pub struct SkillResolver {
    /// All skills from CRDs, keyed by `{namespace}/{name}`.
    store: RwLock<Vec<StoredSkill>>,
    /// Cache of resolved skill sets, keyed by `{tenant}:{tool_ref}:{user_ref}`.
    cache: Cache<String, Arc<Vec<ResolvedSkill>>>,
}

impl SkillResolver {
    /// Create a new resolver with the given cache TTL.
    pub fn new(cache_ttl_secs: u64) -> Self {
        let cache = Cache::builder()
            .time_to_live(std::time::Duration::from_secs(cache_ttl_secs))
            .max_capacity(10_000)
            .build();

        Self {
            store: RwLock::new(Vec::new()),
            cache,
        }
    }

    /// Upsert a skill (insert or update by key).
    pub fn upsert(&self, skill: StoredSkill) {
        let mut store = self.store.write();
        if let Some(existing) = store.iter_mut().find(|s| s.key == skill.key) {
            *existing = skill;
        } else {
            store.push(skill);
        }
        drop(store);
        self.invalidate_cache();
    }

    /// Return the number of stored skills.
    pub fn skill_count(&self) -> usize {
        self.store.read().len()
    }

    /// Remove a skill by key.
    pub fn remove(&self, key: &str) -> bool {
        let mut store = self.store.write();
        let len_before = store.len();
        store.retain(|s| s.key != key);
        let removed = store.len() < len_before;
        drop(store);
        if removed {
            self.invalidate_cache();
        }
        removed
    }

    /// Resolve skills for a given context using CSS cascade ordering.
    ///
    /// Returns skills sorted by specificity desc, then priority desc.
    /// Filters: only enabled skills matching the tenant, and scope-appropriate refs.
    pub fn resolve(
        &self,
        tenant_id: &str,
        tool_ref: Option<&str>,
        user_ref: Option<&str>,
    ) -> Arc<Vec<ResolvedSkill>> {
        let cache_key = format!(
            "{}:{}:{}",
            tenant_id,
            tool_ref.unwrap_or(""),
            user_ref.unwrap_or("")
        );

        if let Some(cached) = self.cache.get(&cache_key) {
            return cached;
        }

        let store = self.store.read();

        let mut filtered: Vec<&StoredSkill> = store
            .iter()
            .filter(|s| {
                if !s.enabled {
                    return false;
                }
                if s.tenant_id != tenant_id {
                    return false;
                }
                match s.scope {
                    SkillScope::Global | SkillScope::Tenant => true,
                    SkillScope::Tool => tool_ref.is_some() && s.tool_ref.as_deref() == tool_ref,
                    SkillScope::User => user_ref.is_some() && s.user_ref.as_deref() == user_ref,
                }
            })
            .collect();

        // Sort by specificity desc, then priority desc (CSS cascade)
        filtered.sort_by(|a, b| {
            let spec_cmp = b.scope.specificity().cmp(&a.scope.specificity());
            if spec_cmp != std::cmp::Ordering::Equal {
                return spec_cmp;
            }
            b.priority.cmp(&a.priority)
        });

        let resolved: Vec<ResolvedSkill> = filtered
            .into_iter()
            .map(|s| ResolvedSkill {
                name: s.name.clone(),
                scope: s.scope,
                priority: s.priority,
                instructions: s.instructions.clone(),
                specificity: s.scope.specificity(),
            })
            .collect();

        let result = Arc::new(resolved);
        self.cache.insert(cache_key, result.clone());
        result
    }

    /// Number of skills in the store.
    pub fn count(&self) -> usize {
        self.store.read().len()
    }

    /// Invalidate the entire cache (called after store mutations).
    fn invalidate_cache(&self) {
        self.cache.invalidate_all();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_skill(key: &str, tenant: &str, scope: SkillScope, priority: u8) -> StoredSkill {
        StoredSkill {
            key: key.to_string(),
            name: key.split('/').next_back().unwrap_or(key).to_string(),
            description: None,
            tenant_id: tenant.to_string(),
            scope,
            priority,
            instructions: Some(format!("Instructions for {}", key)),
            tool_ref: None,
            user_ref: None,
            enabled: true,
        }
    }

    #[test]
    fn test_upsert_and_count() {
        let resolver = SkillResolver::new(300);
        resolver.upsert(make_skill("ns/a", "t1", SkillScope::Tenant, 50));
        assert_eq!(resolver.count(), 1);

        resolver.upsert(make_skill("ns/b", "t1", SkillScope::Global, 30));
        assert_eq!(resolver.count(), 2);

        // Upsert existing key replaces
        resolver.upsert(make_skill("ns/a", "t1", SkillScope::Tenant, 80));
        assert_eq!(resolver.count(), 2);
    }

    #[test]
    fn test_remove() {
        let resolver = SkillResolver::new(300);
        resolver.upsert(make_skill("ns/a", "t1", SkillScope::Tenant, 50));
        assert!(resolver.remove("ns/a"));
        assert_eq!(resolver.count(), 0);
        assert!(!resolver.remove("ns/a")); // Already removed
    }

    #[test]
    fn test_resolve_empty() {
        let resolver = SkillResolver::new(300);
        let result = resolver.resolve("t1", None, None);
        assert!(result.is_empty());
    }

    #[test]
    fn test_resolve_cascade_ordering() {
        let resolver = SkillResolver::new(300);
        resolver.upsert(make_skill("ns/global", "t1", SkillScope::Global, 90));
        resolver.upsert(make_skill("ns/tenant", "t1", SkillScope::Tenant, 50));

        let mut tool_skill = make_skill("ns/tool", "t1", SkillScope::Tool, 50);
        tool_skill.tool_ref = Some("code-review".to_string());
        resolver.upsert(tool_skill);

        let result = resolver.resolve("t1", Some("code-review"), None);
        assert_eq!(result.len(), 3);
        // Tool (specificity 2) first, then Tenant (1), then Global (0)
        assert_eq!(result[0].scope, SkillScope::Tool);
        assert_eq!(result[1].scope, SkillScope::Tenant);
        assert_eq!(result[2].scope, SkillScope::Global);
    }

    #[test]
    fn test_resolve_priority_tiebreaker() {
        let resolver = SkillResolver::new(300);
        resolver.upsert(make_skill("ns/low", "t1", SkillScope::Tenant, 20));
        resolver.upsert(make_skill("ns/high", "t1", SkillScope::Tenant, 80));
        resolver.upsert(make_skill("ns/mid", "t1", SkillScope::Tenant, 50));

        let result = resolver.resolve("t1", None, None);
        assert_eq!(result.len(), 3);
        assert_eq!(result[0].priority, 80);
        assert_eq!(result[1].priority, 50);
        assert_eq!(result[2].priority, 20);
    }

    #[test]
    fn test_resolve_tenant_isolation() {
        let resolver = SkillResolver::new(300);
        resolver.upsert(make_skill("ns/t1skill", "t1", SkillScope::Tenant, 50));
        resolver.upsert(make_skill("ns/t2skill", "t2", SkillScope::Tenant, 50));

        let result = resolver.resolve("t1", None, None);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].name, "t1skill");
    }

    #[test]
    fn test_resolve_disabled_skills_excluded() {
        let resolver = SkillResolver::new(300);
        let mut skill = make_skill("ns/disabled", "t1", SkillScope::Tenant, 50);
        skill.enabled = false;
        resolver.upsert(skill);

        let result = resolver.resolve("t1", None, None);
        assert!(result.is_empty());
    }

    #[test]
    fn test_resolve_tool_scope_requires_matching_ref() {
        let resolver = SkillResolver::new(300);
        let mut skill = make_skill("ns/tool", "t1", SkillScope::Tool, 50);
        skill.tool_ref = Some("code-review".to_string());
        resolver.upsert(skill);

        // No tool_ref → tool-scoped skill excluded
        let result = resolver.resolve("t1", None, None);
        assert!(result.is_empty());

        // Wrong tool_ref → excluded
        let result = resolver.resolve("t1", Some("deploy"), None);
        assert!(result.is_empty());

        // Matching tool_ref → included
        let result = resolver.resolve("t1", Some("code-review"), None);
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn test_resolve_user_scope_requires_matching_ref() {
        let resolver = SkillResolver::new(300);
        let mut skill = make_skill("ns/user", "t1", SkillScope::User, 50);
        skill.user_ref = Some("alice".to_string());
        resolver.upsert(skill);

        let result = resolver.resolve("t1", None, None);
        assert!(result.is_empty());

        let result = resolver.resolve("t1", None, Some("bob"));
        assert!(result.is_empty());

        let result = resolver.resolve("t1", None, Some("alice"));
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn test_cache_invalidation_on_upsert() {
        let resolver = SkillResolver::new(300);
        resolver.upsert(make_skill("ns/a", "t1", SkillScope::Tenant, 50));

        let result1 = resolver.resolve("t1", None, None);
        assert_eq!(result1.len(), 1);

        // Add another skill → cache should be invalidated
        resolver.upsert(make_skill("ns/b", "t1", SkillScope::Tenant, 80));
        let result2 = resolver.resolve("t1", None, None);
        assert_eq!(result2.len(), 2);
    }

    #[test]
    fn test_scope_display() {
        assert_eq!(SkillScope::Global.to_string(), "global");
        assert_eq!(SkillScope::Tenant.to_string(), "tenant");
        assert_eq!(SkillScope::Tool.to_string(), "tool");
        assert_eq!(SkillScope::User.to_string(), "user");
    }

    #[test]
    fn test_scope_from_crd() {
        assert_eq!(SkillScope::from_crd("global"), Some(SkillScope::Global));
        assert_eq!(SkillScope::from_crd("tenant"), Some(SkillScope::Tenant));
        assert_eq!(SkillScope::from_crd("tool"), Some(SkillScope::Tool));
        assert_eq!(SkillScope::from_crd("user"), Some(SkillScope::User));
        assert_eq!(SkillScope::from_crd("invalid"), None);
    }

    #[test]
    fn test_scope_specificity_values() {
        assert_eq!(SkillScope::Global.specificity(), 0);
        assert_eq!(SkillScope::Tenant.specificity(), 1);
        assert_eq!(SkillScope::Tool.specificity(), 2);
        assert_eq!(SkillScope::User.specificity(), 3);
    }
}
