//! GraphQL Schema Introspection (CAB-1756)
//!
//! Parses GraphQL introspection responses to extract types, queries, and mutations.
//! Used to auto-generate MCP tools from a GraphQL backend schema.
//!
//! The introspection query follows the standard GraphQL introspection spec:
//! `{ __schema { queryType { name } mutationType { name } types { ... } } }`

use serde::{Deserialize, Serialize};

/// Standard GraphQL introspection query.
pub const INTROSPECTION_QUERY: &str = r#"
{
  __schema {
    queryType { name }
    mutationType { name }
    types {
      name
      kind
      description
      fields {
        name
        description
        args {
          name
          description
          type {
            name
            kind
            ofType {
              name
              kind
              ofType {
                name
                kind
              }
            }
          }
          defaultValue
        }
        type {
          name
          kind
          ofType {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
    }
  }
}
"#;

/// A parsed GraphQL schema from an introspection response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphQLSchema {
    /// Root query type name (usually "Query")
    pub query_type: Option<String>,
    /// Root mutation type name (usually "Mutation")
    pub mutation_type: Option<String>,
    /// Query fields (operations on the root Query type)
    pub queries: Vec<GraphQLField>,
    /// Mutation fields (operations on the root Mutation type)
    pub mutations: Vec<GraphQLField>,
    /// Named types (objects, enums, input objects, etc.)
    pub types: Vec<GraphQLType>,
}

/// A GraphQL type definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphQLType {
    /// Type name
    pub name: String,
    /// Type kind (OBJECT, INPUT_OBJECT, ENUM, SCALAR, etc.)
    pub kind: String,
    /// Human-readable description
    pub description: Option<String>,
    /// Fields (for OBJECT and INPUT_OBJECT types)
    pub fields: Vec<GraphQLField>,
}

/// A GraphQL field (query, mutation, or object field).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphQLField {
    /// Field name
    pub name: String,
    /// Human-readable description
    pub description: Option<String>,
    /// Arguments (for queries/mutations)
    pub args: Vec<GraphQLArg>,
    /// Return type
    pub return_type: GraphQLTypeRef,
}

/// A GraphQL field argument.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphQLArg {
    /// Argument name
    pub name: String,
    /// Human-readable description
    pub description: Option<String>,
    /// Argument type
    pub arg_type: GraphQLTypeRef,
    /// Default value (as a string)
    pub default_value: Option<String>,
}

/// A reference to a GraphQL type (with NON_NULL/LIST wrappers).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphQLTypeRef {
    /// Type name (None for wrapper types like NON_NULL, LIST)
    pub name: Option<String>,
    /// Type kind
    pub kind: String,
    /// Wrapped type (for NON_NULL or LIST)
    pub of_type: Option<Box<GraphQLTypeRef>>,
}

impl GraphQLTypeRef {
    /// Get the leaf (unwrapped) type name.
    pub fn leaf_name(&self) -> Option<&str> {
        if let Some(ref name) = self.name {
            Some(name)
        } else {
            self.of_type.as_ref().and_then(|t| t.leaf_name())
        }
    }

    /// Check if this type is non-null (required).
    pub fn is_non_null(&self) -> bool {
        self.kind == "NON_NULL"
    }

    /// Check if this type is a list.
    pub fn is_list(&self) -> bool {
        if self.kind == "LIST" {
            return true;
        }
        self.of_type.as_ref().is_some_and(|t| t.is_list())
    }

    /// Convert to a JSON Schema type string.
    pub fn json_schema_type(&self) -> &str {
        let name = self.leaf_name().unwrap_or("String");
        match name {
            "String" | "ID" => "string",
            "Int" => "integer",
            "Float" => "number",
            "Boolean" => "boolean",
            _ => "object",
        }
    }
}

/// Parse a GraphQL introspection response into a `GraphQLSchema`.
///
/// Expects the standard `{ "data": { "__schema": { ... } } }` format.
pub fn parse_introspection(json: &serde_json::Value) -> Result<GraphQLSchema, String> {
    let schema = json
        .get("data")
        .and_then(|d| d.get("__schema"))
        .ok_or("Missing data.__schema in introspection response")?;

    let query_type = schema
        .get("queryType")
        .and_then(|t| t.get("name"))
        .and_then(|n| n.as_str())
        .map(|s| s.to_string());

    let mutation_type = schema
        .get("mutationType")
        .and_then(|t| t.get("name"))
        .and_then(|n| n.as_str())
        .map(|s| s.to_string());

    let raw_types = schema
        .get("types")
        .and_then(|t| t.as_array())
        .cloned()
        .unwrap_or_default();

    let mut types = Vec::new();
    let mut queries = Vec::new();
    let mut mutations = Vec::new();

    for raw_type in &raw_types {
        let name = raw_type
            .get("name")
            .and_then(|n| n.as_str())
            .unwrap_or("")
            .to_string();

        // Skip built-in types (prefixed with __)
        if name.starts_with("__") {
            continue;
        }

        let kind = raw_type
            .get("kind")
            .and_then(|k| k.as_str())
            .unwrap_or("OBJECT")
            .to_string();

        let description = raw_type
            .get("description")
            .and_then(|d| d.as_str())
            .map(|s| s.to_string());

        let fields = parse_fields(raw_type.get("fields"));

        // Collect root query/mutation fields
        if query_type.as_deref() == Some(&name) {
            queries = fields.clone();
        }
        if mutation_type.as_deref() == Some(&name) {
            mutations = fields.clone();
        }

        // Skip scalar types (no useful fields)
        if kind == "SCALAR" {
            continue;
        }

        types.push(GraphQLType {
            name,
            kind,
            description,
            fields,
        });
    }

    Ok(GraphQLSchema {
        query_type,
        mutation_type,
        queries,
        mutations,
        types,
    })
}

/// Parse fields from a JSON array.
fn parse_fields(fields_json: Option<&serde_json::Value>) -> Vec<GraphQLField> {
    let Some(arr) = fields_json.and_then(|f| f.as_array()) else {
        return Vec::new();
    };

    arr.iter()
        .filter_map(|f| {
            let name = f.get("name")?.as_str()?.to_string();
            let description = f
                .get("description")
                .and_then(|d| d.as_str())
                .map(|s| s.to_string());

            let args = parse_args(f.get("args"));
            let return_type = parse_type_ref(f.get("type"));

            Some(GraphQLField {
                name,
                description,
                args,
                return_type,
            })
        })
        .collect()
}

/// Parse arguments from a JSON array.
fn parse_args(args_json: Option<&serde_json::Value>) -> Vec<GraphQLArg> {
    let Some(arr) = args_json.and_then(|a| a.as_array()) else {
        return Vec::new();
    };

    arr.iter()
        .filter_map(|a| {
            let name = a.get("name")?.as_str()?.to_string();
            let description = a
                .get("description")
                .and_then(|d| d.as_str())
                .map(|s| s.to_string());
            let arg_type = parse_type_ref(a.get("type"));
            let default_value = a
                .get("defaultValue")
                .and_then(|d| d.as_str())
                .map(|s| s.to_string());

            Some(GraphQLArg {
                name,
                description,
                arg_type,
                default_value,
            })
        })
        .collect()
}

/// Parse a type reference from JSON (handling NON_NULL/LIST wrappers).
fn parse_type_ref(type_json: Option<&serde_json::Value>) -> GraphQLTypeRef {
    let Some(t) = type_json else {
        return GraphQLTypeRef {
            name: Some("String".to_string()),
            kind: "SCALAR".to_string(),
            of_type: None,
        };
    };

    let name = t
        .get("name")
        .and_then(|n| n.as_str())
        .map(|s| s.to_string());
    let kind = t
        .get("kind")
        .and_then(|k| k.as_str())
        .unwrap_or("SCALAR")
        .to_string();

    let of_type = t.get("ofType").and_then(|ot| {
        if ot.is_null() {
            None
        } else {
            Some(Box::new(parse_type_ref(Some(ot))))
        }
    });

    GraphQLTypeRef {
        name,
        kind,
        of_type,
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_introspection() -> serde_json::Value {
        serde_json::json!({
            "data": {
                "__schema": {
                    "queryType": { "name": "Query" },
                    "mutationType": { "name": "Mutation" },
                    "types": [
                        {
                            "name": "Query",
                            "kind": "OBJECT",
                            "description": "Root query type",
                            "fields": [
                                {
                                    "name": "user",
                                    "description": "Get a user by ID",
                                    "args": [
                                        {
                                            "name": "id",
                                            "description": "User ID",
                                            "type": {
                                                "name": null,
                                                "kind": "NON_NULL",
                                                "ofType": {
                                                    "name": "ID",
                                                    "kind": "SCALAR",
                                                    "ofType": null
                                                }
                                            },
                                            "defaultValue": null
                                        }
                                    ],
                                    "type": {
                                        "name": "User",
                                        "kind": "OBJECT",
                                        "ofType": null
                                    }
                                },
                                {
                                    "name": "users",
                                    "description": "List all users",
                                    "args": [
                                        {
                                            "name": "limit",
                                            "description": "Max results",
                                            "type": {
                                                "name": "Int",
                                                "kind": "SCALAR",
                                                "ofType": null
                                            },
                                            "defaultValue": "10"
                                        }
                                    ],
                                    "type": {
                                        "name": null,
                                        "kind": "LIST",
                                        "ofType": {
                                            "name": "User",
                                            "kind": "OBJECT",
                                            "ofType": null
                                        }
                                    }
                                }
                            ]
                        },
                        {
                            "name": "Mutation",
                            "kind": "OBJECT",
                            "description": null,
                            "fields": [
                                {
                                    "name": "createUser",
                                    "description": "Create a new user",
                                    "args": [
                                        {
                                            "name": "name",
                                            "description": "User name",
                                            "type": {
                                                "name": null,
                                                "kind": "NON_NULL",
                                                "ofType": {
                                                    "name": "String",
                                                    "kind": "SCALAR",
                                                    "ofType": null
                                                }
                                            },
                                            "defaultValue": null
                                        },
                                        {
                                            "name": "email",
                                            "description": "Email address",
                                            "type": {
                                                "name": "String",
                                                "kind": "SCALAR",
                                                "ofType": null
                                            },
                                            "defaultValue": null
                                        }
                                    ],
                                    "type": {
                                        "name": "User",
                                        "kind": "OBJECT",
                                        "ofType": null
                                    }
                                }
                            ]
                        },
                        {
                            "name": "User",
                            "kind": "OBJECT",
                            "description": "A user in the system",
                            "fields": [
                                {
                                    "name": "id",
                                    "description": null,
                                    "args": [],
                                    "type": { "name": "ID", "kind": "SCALAR", "ofType": null }
                                },
                                {
                                    "name": "name",
                                    "description": null,
                                    "args": [],
                                    "type": { "name": "String", "kind": "SCALAR", "ofType": null }
                                },
                                {
                                    "name": "email",
                                    "description": null,
                                    "args": [],
                                    "type": { "name": "String", "kind": "SCALAR", "ofType": null }
                                }
                            ]
                        },
                        {
                            "name": "__Schema",
                            "kind": "OBJECT",
                            "description": "Built-in",
                            "fields": []
                        },
                        {
                            "name": "String",
                            "kind": "SCALAR",
                            "description": "Built-in String",
                            "fields": null
                        }
                    ]
                }
            }
        })
    }

    #[test]
    fn test_parse_introspection_basic() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        assert_eq!(schema.query_type, Some("Query".to_string()));
        assert_eq!(schema.mutation_type, Some("Mutation".to_string()));
    }

    #[test]
    fn test_parse_queries() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        assert_eq!(schema.queries.len(), 2);
        assert_eq!(schema.queries[0].name, "user");
        assert_eq!(schema.queries[1].name, "users");
    }

    #[test]
    fn test_parse_mutations() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        assert_eq!(schema.mutations.len(), 1);
        assert_eq!(schema.mutations[0].name, "createUser");
    }

    #[test]
    fn test_parse_query_args() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        let user_query = &schema.queries[0];
        assert_eq!(user_query.args.len(), 1);
        assert_eq!(user_query.args[0].name, "id");
        assert!(user_query.args[0].arg_type.is_non_null());
    }

    #[test]
    fn test_parse_mutation_args() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        let create = &schema.mutations[0];
        assert_eq!(create.args.len(), 2);
        assert_eq!(create.args[0].name, "name");
        assert!(create.args[0].arg_type.is_non_null());
        assert_eq!(create.args[1].name, "email");
        assert!(!create.args[1].arg_type.is_non_null());
    }

    #[test]
    fn test_type_ref_leaf_name() {
        let non_null = GraphQLTypeRef {
            name: None,
            kind: "NON_NULL".to_string(),
            of_type: Some(Box::new(GraphQLTypeRef {
                name: Some("String".to_string()),
                kind: "SCALAR".to_string(),
                of_type: None,
            })),
        };
        assert_eq!(non_null.leaf_name(), Some("String"));
    }

    #[test]
    fn test_type_ref_is_list() {
        let list_type = GraphQLTypeRef {
            name: None,
            kind: "LIST".to_string(),
            of_type: Some(Box::new(GraphQLTypeRef {
                name: Some("User".to_string()),
                kind: "OBJECT".to_string(),
                of_type: None,
            })),
        };
        assert!(list_type.is_list());

        let scalar_type = GraphQLTypeRef {
            name: Some("String".to_string()),
            kind: "SCALAR".to_string(),
            of_type: None,
        };
        assert!(!scalar_type.is_list());
    }

    #[test]
    fn test_type_ref_json_schema_type() {
        let string_type = GraphQLTypeRef {
            name: Some("String".to_string()),
            kind: "SCALAR".to_string(),
            of_type: None,
        };
        assert_eq!(string_type.json_schema_type(), "string");

        let int_type = GraphQLTypeRef {
            name: Some("Int".to_string()),
            kind: "SCALAR".to_string(),
            of_type: None,
        };
        assert_eq!(int_type.json_schema_type(), "integer");

        let object_type = GraphQLTypeRef {
            name: Some("User".to_string()),
            kind: "OBJECT".to_string(),
            of_type: None,
        };
        assert_eq!(object_type.json_schema_type(), "object");
    }

    #[test]
    fn test_skips_builtin_types() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        // __Schema should be skipped, String (SCALAR) should be skipped
        for t in &schema.types {
            assert!(!t.name.starts_with("__"));
            assert_ne!(t.kind, "SCALAR");
        }
    }

    #[test]
    fn test_user_type_fields() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        let user_type = schema
            .types
            .iter()
            .find(|t| t.name == "User")
            .expect("User");
        assert_eq!(user_type.fields.len(), 3);
        assert_eq!(user_type.fields[0].name, "id");
        assert_eq!(user_type.fields[1].name, "name");
        assert_eq!(user_type.fields[2].name, "email");
    }

    #[test]
    fn test_default_value_preserved() {
        let json = sample_introspection();
        let schema = parse_introspection(&json).expect("should parse");
        let users_query = &schema.queries[1];
        assert_eq!(users_query.args[0].default_value, Some("10".to_string()));
    }

    #[test]
    fn test_parse_introspection_missing_schema() {
        let bad = serde_json::json!({"data": {}});
        assert!(parse_introspection(&bad).is_err());
    }

    #[test]
    fn test_parse_introspection_no_mutation() {
        let json = serde_json::json!({
            "data": {
                "__schema": {
                    "queryType": { "name": "Query" },
                    "mutationType": null,
                    "types": [
                        {
                            "name": "Query",
                            "kind": "OBJECT",
                            "description": null,
                            "fields": [
                                {
                                    "name": "hello",
                                    "description": "Say hello",
                                    "args": [],
                                    "type": { "name": "String", "kind": "SCALAR", "ofType": null }
                                }
                            ]
                        }
                    ]
                }
            }
        });
        let schema = parse_introspection(&json).expect("should parse");
        assert!(schema.mutation_type.is_none());
        assert!(schema.mutations.is_empty());
        assert_eq!(schema.queries.len(), 1);
        assert_eq!(schema.queries[0].name, "hello");
    }
}
