#![no_main]

// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

use libfuzzer_sys::fuzz_target;
use stoa_policy_engine::policy::PolicyEngine;

fuzz_target!(|data: &str| {
    // Try to parse arbitrary strings as YAML config
    // This should never panic, only return errors
    let _ = PolicyEngine::from_yaml(data);
});
