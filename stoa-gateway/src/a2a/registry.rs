//! A2A Agent Registry (CAB-1754)
//!
//! In-memory registry of agent cards. Agents can be registered via the admin API
//! or discovered from upstream MCP tools that declare A2A capabilities.

use std::collections::HashMap;
use std::sync::RwLock;

use super::types::{AgentCard, Task, TaskState, TaskStatus};

/// Registry of known A2A agents and their tasks.
pub struct AgentRegistry {
    /// Registered agent cards, keyed by agent name
    agents: RwLock<HashMap<String, AgentCard>>,
    /// In-flight tasks, keyed by task ID
    tasks: RwLock<HashMap<String, Task>>,
    /// Max agents allowed (prevents unbounded growth)
    max_agents: usize,
    /// Max tasks in memory (LRU eviction when exceeded)
    max_tasks: usize,
}

impl AgentRegistry {
    pub fn new(max_agents: usize, max_tasks: usize) -> Self {
        Self {
            agents: RwLock::new(HashMap::new()),
            tasks: RwLock::new(HashMap::new()),
            max_agents,
            max_tasks,
        }
    }

    // ─── Agent Card Operations ───

    /// Register or update an agent card.
    /// Returns true if the agent was newly registered, false if updated.
    pub fn register_agent(&self, card: AgentCard) -> Result<bool, RegistryError> {
        let mut agents = self
            .agents
            .write()
            .map_err(|_| RegistryError::LockPoisoned)?;

        if agents.len() >= self.max_agents && !agents.contains_key(&card.name) {
            return Err(RegistryError::CapacityExceeded {
                max: self.max_agents,
            });
        }

        let is_new = !agents.contains_key(&card.name);
        agents.insert(card.name.clone(), card);
        Ok(is_new)
    }

    /// Remove an agent by name.
    pub fn unregister_agent(&self, name: &str) -> Result<bool, RegistryError> {
        let mut agents = self
            .agents
            .write()
            .map_err(|_| RegistryError::LockPoisoned)?;
        Ok(agents.remove(name).is_some())
    }

    /// Get an agent card by name.
    pub fn get_agent(&self, name: &str) -> Result<Option<AgentCard>, RegistryError> {
        let agents = self
            .agents
            .read()
            .map_err(|_| RegistryError::LockPoisoned)?;
        Ok(agents.get(name).cloned())
    }

    /// List all registered agent cards.
    pub fn list_agents(&self) -> Result<Vec<AgentCard>, RegistryError> {
        let agents = self
            .agents
            .read()
            .map_err(|_| RegistryError::LockPoisoned)?;
        Ok(agents.values().cloned().collect())
    }

    /// Number of registered agents.
    pub fn agent_count(&self) -> Result<usize, RegistryError> {
        let agents = self
            .agents
            .read()
            .map_err(|_| RegistryError::LockPoisoned)?;
        Ok(agents.len())
    }

    // ─── Task Operations ───

    /// Store a new task.
    pub fn store_task(&self, task: Task) -> Result<(), RegistryError> {
        let mut tasks = self
            .tasks
            .write()
            .map_err(|_| RegistryError::LockPoisoned)?;

        // Evict oldest completed tasks if at capacity
        if tasks.len() >= self.max_tasks {
            let completed_keys: Vec<String> = tasks
                .iter()
                .filter(|(_, t)| {
                    matches!(
                        t.status.state,
                        TaskState::Completed | TaskState::Failed | TaskState::Canceled
                    )
                })
                .map(|(k, _)| k.clone())
                .collect();

            for key in completed_keys.iter().take(self.max_tasks / 4) {
                tasks.remove(key);
            }

            if tasks.len() >= self.max_tasks {
                return Err(RegistryError::CapacityExceeded {
                    max: self.max_tasks,
                });
            }
        }

        tasks.insert(task.id.clone(), task);
        Ok(())
    }

    /// Get a task by ID.
    pub fn get_task(&self, id: &str) -> Result<Option<Task>, RegistryError> {
        let tasks = self.tasks.read().map_err(|_| RegistryError::LockPoisoned)?;
        Ok(tasks.get(id).cloned())
    }

    /// Update task status.
    pub fn update_task_status(&self, id: &str, status: TaskStatus) -> Result<bool, RegistryError> {
        let mut tasks = self
            .tasks
            .write()
            .map_err(|_| RegistryError::LockPoisoned)?;

        if let Some(task) = tasks.get_mut(id) {
            task.status = status;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    /// Cancel a task (only if in submitted or working state).
    pub fn cancel_task(&self, id: &str) -> Result<bool, RegistryError> {
        let mut tasks = self
            .tasks
            .write()
            .map_err(|_| RegistryError::LockPoisoned)?;

        if let Some(task) = tasks.get_mut(id) {
            match task.status.state {
                TaskState::Submitted | TaskState::Working | TaskState::InputRequired => {
                    task.status = TaskStatus {
                        state: TaskState::Canceled,
                        message: None,
                        timestamp: Some(chrono::Utc::now().to_rfc3339()),
                    };
                    Ok(true)
                }
                _ => Ok(false), // Already terminal
            }
        } else {
            Ok(false)
        }
    }
}

/// Registry errors
#[derive(Debug, thiserror::Error)]
pub enum RegistryError {
    #[error("registry lock poisoned")]
    LockPoisoned,
    #[error("capacity exceeded: max {max}")]
    CapacityExceeded { max: usize },
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::a2a::types::*;

    fn test_card(name: &str) -> AgentCard {
        AgentCard {
            name: name.to_string(),
            description: format!("Test agent {name}"),
            url: format!("https://example.com/agents/{name}"),
            protocol_version: A2A_PROTOCOL_VERSION.to_string(),
            capabilities: AgentCapabilities {
                streaming: false,
                push_notifications: false,
                state_transition_history: false,
            },
            authentication: None,
            skills: vec![],
            provider: None,
        }
    }

    fn test_task(id: &str) -> Task {
        Task {
            id: id.to_string(),
            session_id: None,
            status: TaskStatus {
                state: TaskState::Submitted,
                message: None,
                timestamp: None,
            },
            history: vec![],
            artifacts: vec![],
            metadata: Default::default(),
        }
    }

    #[test]
    fn test_register_and_list_agents() {
        let reg = AgentRegistry::new(10, 100);
        assert!(reg.register_agent(test_card("alpha")).unwrap());
        assert!(reg.register_agent(test_card("beta")).unwrap());
        assert_eq!(reg.agent_count().unwrap(), 2);

        let agents = reg.list_agents().unwrap();
        assert_eq!(agents.len(), 2);
    }

    #[test]
    fn test_register_agent_update() {
        let reg = AgentRegistry::new(10, 100);
        assert!(reg.register_agent(test_card("alpha")).unwrap());
        // Second register is an update, returns false
        assert!(!reg.register_agent(test_card("alpha")).unwrap());
        assert_eq!(reg.agent_count().unwrap(), 1);
    }

    #[test]
    fn test_register_agent_capacity() {
        let reg = AgentRegistry::new(2, 100);
        assert!(reg.register_agent(test_card("a")).unwrap());
        assert!(reg.register_agent(test_card("b")).unwrap());
        assert!(matches!(
            reg.register_agent(test_card("c")),
            Err(RegistryError::CapacityExceeded { max: 2 })
        ));
    }

    #[test]
    fn test_unregister_agent() {
        let reg = AgentRegistry::new(10, 100);
        reg.register_agent(test_card("alpha")).unwrap();
        assert!(reg.unregister_agent("alpha").unwrap());
        assert!(!reg.unregister_agent("alpha").unwrap());
        assert_eq!(reg.agent_count().unwrap(), 0);
    }

    #[test]
    fn test_get_agent() {
        let reg = AgentRegistry::new(10, 100);
        reg.register_agent(test_card("alpha")).unwrap();
        let card = reg.get_agent("alpha").unwrap().unwrap();
        assert_eq!(card.name, "alpha");
        assert!(reg.get_agent("nonexistent").unwrap().is_none());
    }

    #[test]
    fn test_store_and_get_task() {
        let reg = AgentRegistry::new(10, 100);
        reg.store_task(test_task("t1")).unwrap();
        let task = reg.get_task("t1").unwrap().unwrap();
        assert_eq!(task.id, "t1");
        assert_eq!(task.status.state, TaskState::Submitted);
    }

    #[test]
    fn test_update_task_status() {
        let reg = AgentRegistry::new(10, 100);
        reg.store_task(test_task("t1")).unwrap();
        let updated = reg
            .update_task_status(
                "t1",
                TaskStatus {
                    state: TaskState::Working,
                    message: None,
                    timestamp: None,
                },
            )
            .unwrap();
        assert!(updated);

        let task = reg.get_task("t1").unwrap().unwrap();
        assert_eq!(task.status.state, TaskState::Working);
    }

    #[test]
    fn test_cancel_task() {
        let reg = AgentRegistry::new(10, 100);
        reg.store_task(test_task("t1")).unwrap();
        assert!(reg.cancel_task("t1").unwrap());

        let task = reg.get_task("t1").unwrap().unwrap();
        assert_eq!(task.status.state, TaskState::Canceled);

        // Can't cancel already canceled task
        assert!(!reg.cancel_task("t1").unwrap());
    }

    #[test]
    fn test_cancel_completed_task_fails() {
        let reg = AgentRegistry::new(10, 100);
        reg.store_task(test_task("t1")).unwrap();
        reg.update_task_status(
            "t1",
            TaskStatus {
                state: TaskState::Completed,
                message: None,
                timestamp: None,
            },
        )
        .unwrap();
        // Completed tasks cannot be canceled
        assert!(!reg.cancel_task("t1").unwrap());
    }

    #[test]
    fn test_task_not_found() {
        let reg = AgentRegistry::new(10, 100);
        assert!(reg.get_task("nonexistent").unwrap().is_none());
        assert!(!reg.cancel_task("nonexistent").unwrap());
    }

    #[test]
    fn test_task_capacity_eviction() {
        let reg = AgentRegistry::new(10, 4);
        for i in 0..4 {
            reg.store_task(test_task(&format!("t{i}"))).unwrap();
        }
        // Mark some as completed to allow eviction
        reg.update_task_status(
            "t0",
            TaskStatus {
                state: TaskState::Completed,
                message: None,
                timestamp: None,
            },
        )
        .unwrap();
        reg.update_task_status(
            "t1",
            TaskStatus {
                state: TaskState::Completed,
                message: None,
                timestamp: None,
            },
        )
        .unwrap();
        // Now adding a new task should succeed (evicts completed ones)
        assert!(reg.store_task(test_task("t4")).is_ok());
    }
}
