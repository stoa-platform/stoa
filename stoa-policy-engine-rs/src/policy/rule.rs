use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::policy::violation::PolicyViolation;

/// Operators supported for rule evaluation
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum Operator {
    /// Field must be present and non-null
    Required,
    /// Field equals value
    Eq,
    /// Field not equals value
    Neq,
    /// Field less than value
    Lt,
    /// Field less than or equal to value
    Lte,
    /// Field greater than value
    Gt,
    /// Field greater than or equal to value
    Gte,
    /// Field contains value (string or array)
    Contains,
    /// Field matches regex pattern
    Matches,
}

/// A rule definition for policy evaluation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Rule {
    pub field: String,
    pub operator: Operator,
    #[serde(default)]
    pub value: Option<Value>,
    pub message: String,
}

impl Rule {
    /// Check if the given arguments satisfy this rule
    pub fn check(&self, args: &Value) -> Result<(), PolicyViolation> {
        let field_value = self.extract_field(args);

        match self.operator {
            Operator::Required => {
                if field_value.is_none() || field_value == Some(&Value::Null) {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Eq => {
                if field_value != self.value.as_ref() {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Neq => {
                if field_value == self.value.as_ref() {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Lt => {
                if !self.compare_numbers(field_value, |fv, rv| fv < rv) {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Lte => {
                if !self.compare_numbers(field_value, |fv, rv| fv <= rv) {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Gt => {
                if !self.compare_numbers(field_value, |fv, rv| fv > rv) {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Gte => {
                if !self.compare_numbers(field_value, |fv, rv| fv >= rv) {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Contains => {
                if !self.check_contains(field_value) {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
            Operator::Matches => {
                if !self.check_matches(field_value) {
                    return Err(PolicyViolation::new(&self.field, &self.message));
                }
            }
        }

        Ok(())
    }

    /// Extract a field value from arguments, supporting nested fields with dot notation
    fn extract_field<'a>(&self, args: &'a Value) -> Option<&'a Value> {
        self.field.split('.').try_fold(args, |v, key| v.get(key))
    }

    /// Compare numeric values using the provided comparator
    fn compare_numbers<F>(&self, field_value: Option<&Value>, comparator: F) -> bool
    where
        F: Fn(f64, f64) -> bool,
    {
        match (field_value, self.value.as_ref()) {
            (Some(Value::Number(fv)), Some(Value::Number(rv))) => {
                match (fv.as_f64(), rv.as_f64()) {
                    (Some(fv_f64), Some(rv_f64)) => comparator(fv_f64, rv_f64),
                    _ => false,
                }
            }
            _ => false,
        }
    }

    /// Check if field contains the rule value
    fn check_contains(&self, field_value: Option<&Value>) -> bool {
        match (field_value, self.value.as_ref()) {
            // String contains substring
            (Some(Value::String(field_str)), Some(Value::String(search_str))) => {
                field_str.contains(search_str.as_str())
            }
            // Array contains value
            (Some(Value::Array(arr)), Some(search_val)) => arr.contains(search_val),
            _ => false,
        }
    }

    /// Check if field matches the regex pattern
    fn check_matches(&self, field_value: Option<&Value>) -> bool {
        match (field_value, self.value.as_ref()) {
            (Some(Value::String(field_str)), Some(Value::String(pattern))) => {
                match Regex::new(pattern) {
                    Ok(re) => re.is_match(field_str),
                    Err(_) => false,
                }
            }
            _ => false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_operator_required_passes() {
        let rule = Rule {
            field: "cycle".to_string(),
            operator: Operator::Required,
            value: None,
            message: "Cycle is required".to_string(),
        };
        let args = json!({"cycle": "Cycle 42"});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_required_fails_missing() {
        let rule = Rule {
            field: "cycle".to_string(),
            operator: Operator::Required,
            value: None,
            message: "Cycle is required".to_string(),
        };
        let args = json!({"title": "Fix bug"});
        assert!(rule.check(&args).is_err());
    }

    #[test]
    fn test_operator_required_fails_null() {
        let rule = Rule {
            field: "cycle".to_string(),
            operator: Operator::Required,
            value: None,
            message: "Cycle is required".to_string(),
        };
        let args = json!({"cycle": null});
        assert!(rule.check(&args).is_err());
    }

    #[test]
    fn test_operator_eq_passes() {
        let rule = Rule {
            field: "priority".to_string(),
            operator: Operator::Eq,
            value: Some(json!("high")),
            message: "Priority must be high".to_string(),
        };
        let args = json!({"priority": "high"});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_eq_fails() {
        let rule = Rule {
            field: "priority".to_string(),
            operator: Operator::Eq,
            value: Some(json!("high")),
            message: "Priority must be high".to_string(),
        };
        let args = json!({"priority": "low"});
        assert!(rule.check(&args).is_err());
    }

    #[test]
    fn test_operator_neq_passes() {
        let rule = Rule {
            field: "priority".to_string(),
            operator: Operator::Neq,
            value: Some(json!("critical")),
            message: "Priority must not be critical".to_string(),
        };
        let args = json!({"priority": "high"});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_neq_fails() {
        let rule = Rule {
            field: "priority".to_string(),
            operator: Operator::Neq,
            value: Some(json!("critical")),
            message: "Priority must not be critical".to_string(),
        };
        let args = json!({"priority": "critical"});
        assert!(rule.check(&args).is_err());
    }

    #[test]
    fn test_operator_lte_passes() {
        let rule = Rule {
            field: "amount".to_string(),
            operator: Operator::Lte,
            value: Some(json!(10000)),
            message: "Amount must be <= 10000".to_string(),
        };
        let args = json!({"amount": 5000});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_lte_fails() {
        let rule = Rule {
            field: "amount".to_string(),
            operator: Operator::Lte,
            value: Some(json!(10000)),
            message: "Amount must be <= 10000".to_string(),
        };
        let args = json!({"amount": 15000});
        assert!(rule.check(&args).is_err());
    }

    #[test]
    fn test_operator_gt_passes() {
        let rule = Rule {
            field: "count".to_string(),
            operator: Operator::Gt,
            value: Some(json!(0)),
            message: "Count must be > 0".to_string(),
        };
        let args = json!({"count": 5});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_contains_string_passes() {
        let rule = Rule {
            field: "email".to_string(),
            operator: Operator::Contains,
            value: Some(json!("@company.com")),
            message: "Email must be company email".to_string(),
        };
        let args = json!({"email": "user@company.com"});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_contains_array_passes() {
        let rule = Rule {
            field: "tags".to_string(),
            operator: Operator::Contains,
            value: Some(json!("approved")),
            message: "Tags must contain approved".to_string(),
        };
        let args = json!({"tags": ["pending", "approved", "reviewed"]});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_matches_passes() {
        let rule = Rule {
            field: "code".to_string(),
            operator: Operator::Matches,
            value: Some(json!("^[A-Z]{3}-[0-9]{4}$")),
            message: "Code must match pattern".to_string(),
        };
        let args = json!({"code": "ABC-1234"});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_operator_matches_fails() {
        let rule = Rule {
            field: "code".to_string(),
            operator: Operator::Matches,
            value: Some(json!("^[A-Z]{3}-[0-9]{4}$")),
            message: "Code must match pattern".to_string(),
        };
        let args = json!({"code": "invalid"});
        assert!(rule.check(&args).is_err());
    }

    #[test]
    fn test_nested_field_extraction() {
        let rule = Rule {
            field: "user.role".to_string(),
            operator: Operator::Eq,
            value: Some(json!("admin")),
            message: "User role must be admin".to_string(),
        };
        let args = json!({"user": {"role": "admin", "name": "John"}});
        assert!(rule.check(&args).is_ok());
    }

    #[test]
    fn test_deeply_nested_field() {
        let rule = Rule {
            field: "data.user.permissions.level".to_string(),
            operator: Operator::Gte,
            value: Some(json!(5)),
            message: "Permission level must be >= 5".to_string(),
        };
        let args = json!({
            "data": {
                "user": {
                    "permissions": {
                        "level": 10
                    }
                }
            }
        });
        assert!(rule.check(&args).is_ok());
    }
}
