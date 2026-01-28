// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! STOA Policy Engine CLI
//!
//! A command-line interface for validating tool calls against policies.

use std::fs;
use std::io::{self, BufRead, Write};
use std::path::PathBuf;
use std::process::ExitCode;

use stoa_policy_engine::mcp::ToolCall;
use stoa_policy_engine::policy::PolicyEngine;

const HELP: &str = r#"
STOA Policy Engine CLI

USAGE:
    stoa-policy [OPTIONS] <COMMAND>

COMMANDS:
    validate    Validate a tool call against policies
    check       Check if policy file is valid
    repl        Start interactive REPL mode

OPTIONS:
    -p, --policies <FILE>    Path to policies YAML file
    -h, --help               Print help information
    -V, --version            Print version information

EXAMPLES:
    # Validate a tool call from JSON
    stoa-policy validate -p policies.yaml '{"name": "Linear:create_issue", "arguments": {"title": "Test", "cycle": "Cycle 1"}}'

    # Check policy file syntax
    stoa-policy check -p policies.yaml

    # Interactive REPL mode
    stoa-policy repl -p policies.yaml
"#;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 2 {
        eprintln!("{}", HELP);
        return ExitCode::FAILURE;
    }

    match args[1].as_str() {
        "-h" | "--help" | "help" => {
            println!("{}", HELP);
            ExitCode::SUCCESS
        }
        "-V" | "--version" | "version" => {
            println!("stoa-policy {}", stoa_policy_engine::VERSION);
            ExitCode::SUCCESS
        }
        "validate" => run_validate(&args[2..]),
        "check" => run_check(&args[2..]),
        "repl" => run_repl(&args[2..]),
        cmd => {
            eprintln!("Unknown command: {}", cmd);
            eprintln!("{}", HELP);
            ExitCode::FAILURE
        }
    }
}

fn parse_policies_arg(args: &[String]) -> Option<PathBuf> {
    for i in 0..args.len() {
        if (args[i] == "-p" || args[i] == "--policies") && i + 1 < args.len() {
            return Some(PathBuf::from(&args[i + 1]));
        }
    }
    None
}

fn load_engine(policies_path: &PathBuf) -> Result<PolicyEngine, String> {
    let yaml = fs::read_to_string(policies_path)
        .map_err(|e| format!("Failed to read policies file: {}", e))?;

    PolicyEngine::from_yaml(&yaml).map_err(|e| format!("Failed to parse policies: {}", e))
}

fn run_validate(args: &[String]) -> ExitCode {
    let policies_path = match parse_policies_arg(args) {
        Some(p) => p,
        None => {
            eprintln!("Error: --policies argument required");
            return ExitCode::FAILURE;
        }
    };

    let engine = match load_engine(&policies_path) {
        Ok(e) => e,
        Err(e) => {
            eprintln!("{}", e);
            return ExitCode::FAILURE;
        }
    };

    // Find the JSON argument (last non-flag argument)
    let json_arg = args.iter().find(|a| a.starts_with('{'));

    let tool_call: ToolCall = match json_arg {
        Some(json) => match serde_json::from_str(json) {
            Ok(tc) => tc,
            Err(e) => {
                eprintln!("Failed to parse tool call JSON: {}", e);
                return ExitCode::FAILURE;
            }
        },
        None => {
            eprintln!("Error: tool call JSON required");
            return ExitCode::FAILURE;
        }
    };

    match engine.evaluate(&tool_call) {
        Ok(()) => {
            println!("OK: Tool call passed all policy checks");
            ExitCode::SUCCESS
        }
        Err(violation) => {
            eprintln!("VIOLATION: {}", violation);
            let mcp_error = violation.to_mcp_error();
            println!(
                "MCP Error Response:\n{}",
                serde_json::to_string_pretty(&mcp_error).unwrap()
            );
            ExitCode::FAILURE
        }
    }
}

fn run_check(args: &[String]) -> ExitCode {
    let policies_path = match parse_policies_arg(args) {
        Some(p) => p,
        None => {
            eprintln!("Error: --policies argument required");
            return ExitCode::FAILURE;
        }
    };

    match load_engine(&policies_path) {
        Ok(engine) => {
            println!(
                "OK: Policy file is valid ({} policies, {} enabled)",
                engine.policy_count(),
                engine.enabled_policy_count()
            );
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("{}", e);
            ExitCode::FAILURE
        }
    }
}

fn run_repl(args: &[String]) -> ExitCode {
    let policies_path = match parse_policies_arg(args) {
        Some(p) => p,
        None => {
            eprintln!("Error: --policies argument required");
            return ExitCode::FAILURE;
        }
    };

    let engine = match load_engine(&policies_path) {
        Ok(e) => e,
        Err(e) => {
            eprintln!("{}", e);
            return ExitCode::FAILURE;
        }
    };

    println!("STOA Policy Engine REPL");
    println!(
        "Loaded {} policies ({} enabled)",
        engine.policy_count(),
        engine.enabled_policy_count()
    );
    println!("Enter tool calls as JSON, or 'quit' to exit.\n");

    let stdin = io::stdin();
    let mut stdout = io::stdout();

    loop {
        print!("> ");
        stdout.flush().unwrap();

        let mut line = String::new();
        if stdin.lock().read_line(&mut line).is_err() {
            break;
        }

        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        if line == "quit" || line == "exit" {
            break;
        }

        let tool_call: ToolCall = match serde_json::from_str(line) {
            Ok(tc) => tc,
            Err(e) => {
                eprintln!("Parse error: {}", e);
                continue;
            }
        };

        match engine.evaluate(&tool_call) {
            Ok(()) => println!("OK"),
            Err(violation) => {
                eprintln!("VIOLATION: {}", violation);
            }
        }
    }

    ExitCode::SUCCESS
}
