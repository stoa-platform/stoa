//! Skill Context — resolved skills injected into request extensions (CAB-1365)
//!
//! After the skills middleware resolves the CSS cascade, this context is
//! inserted into request extensions so downstream handlers can access it.

use serde::Serialize;

use super::resolver::ResolvedSkill;

/// Resolved skills context available in request extensions.
///
/// Inserted by the skills middleware after CSS cascade resolution.
/// Handlers read this to build `ToolContext.skill_instructions`.
#[derive(Debug, Clone, Serialize)]
pub struct SkillContext {
    /// Resolved skills ordered by specificity desc, then priority desc.
    pub skills: Vec<ResolvedSkillEntry>,
    /// Concatenated instructions from all resolved skills (for injection).
    pub merged_instructions: String,
    /// Number of skills resolved.
    pub count: usize,
}

/// A single resolved skill entry (serializable for admin API).
#[derive(Debug, Clone, Serialize)]
pub struct ResolvedSkillEntry {
    pub name: String,
    pub scope: String,
    pub priority: u8,
    pub specificity: u8,
    pub instructions: Option<String>,
}

impl SkillContext {
    /// Build a SkillContext from resolved skills.
    ///
    /// Concatenates all non-empty instructions with double-newline separators,
    /// respecting cascade order (highest specificity first).
    pub fn from_resolved(skills: &[ResolvedSkill]) -> Self {
        let entries: Vec<ResolvedSkillEntry> = skills
            .iter()
            .map(|s| ResolvedSkillEntry {
                name: s.name.clone(),
                scope: s.scope.to_string(),
                priority: s.priority,
                specificity: s.specificity,
                instructions: s.instructions.clone(),
            })
            .collect();

        let merged: String = skills
            .iter()
            .filter_map(|s| s.instructions.as_deref())
            .filter(|i| !i.is_empty())
            .collect::<Vec<_>>()
            .join("\n\n");

        let count = entries.len();

        Self {
            skills: entries,
            merged_instructions: merged,
            count,
        }
    }

    /// Returns true if no skills were resolved.
    pub fn is_empty(&self) -> bool {
        self.count == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::skills::resolver::{ResolvedSkill, SkillScope};

    #[test]
    fn test_empty_context() {
        let ctx = SkillContext::from_resolved(&[]);
        assert!(ctx.is_empty());
        assert_eq!(ctx.count, 0);
        assert!(ctx.merged_instructions.is_empty());
        assert!(ctx.skills.is_empty());
    }

    #[test]
    fn test_single_skill() {
        let skills = vec![ResolvedSkill {
            name: "code-style".to_string(),
            scope: SkillScope::Tenant,
            priority: 50,
            instructions: Some("Use Rust 2021 edition.".to_string()),
            specificity: 1,
        }];

        let ctx = SkillContext::from_resolved(&skills);
        assert_eq!(ctx.count, 1);
        assert!(!ctx.is_empty());
        assert_eq!(ctx.merged_instructions, "Use Rust 2021 edition.");
        assert_eq!(ctx.skills[0].name, "code-style");
        assert_eq!(ctx.skills[0].scope, "tenant");
    }

    #[test]
    fn test_merged_instructions_cascade_order() {
        let skills = vec![
            ResolvedSkill {
                name: "user-pref".to_string(),
                scope: SkillScope::User,
                priority: 50,
                instructions: Some("Be concise.".to_string()),
                specificity: 3,
            },
            ResolvedSkill {
                name: "tenant-style".to_string(),
                scope: SkillScope::Tenant,
                priority: 50,
                instructions: Some("Use formal tone.".to_string()),
                specificity: 1,
            },
            ResolvedSkill {
                name: "global-base".to_string(),
                scope: SkillScope::Global,
                priority: 30,
                instructions: Some("Follow MCP protocol.".to_string()),
                specificity: 0,
            },
        ];

        let ctx = SkillContext::from_resolved(&skills);
        assert_eq!(ctx.count, 3);
        // Merged in cascade order (user first, then tenant, then global)
        assert_eq!(
            ctx.merged_instructions,
            "Be concise.\n\nUse formal tone.\n\nFollow MCP protocol."
        );
    }

    #[test]
    fn test_empty_instructions_skipped() {
        let skills = vec![
            ResolvedSkill {
                name: "with-instr".to_string(),
                scope: SkillScope::Tenant,
                priority: 50,
                instructions: Some("Do X.".to_string()),
                specificity: 1,
            },
            ResolvedSkill {
                name: "no-instr".to_string(),
                scope: SkillScope::Global,
                priority: 30,
                instructions: None,
                specificity: 0,
            },
            ResolvedSkill {
                name: "empty-instr".to_string(),
                scope: SkillScope::Global,
                priority: 20,
                instructions: Some(String::new()),
                specificity: 0,
            },
        ];

        let ctx = SkillContext::from_resolved(&skills);
        assert_eq!(ctx.count, 3);
        // Only non-empty instructions included
        assert_eq!(ctx.merged_instructions, "Do X.");
    }
}
