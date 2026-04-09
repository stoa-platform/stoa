// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM

// Package redact provides PII masking utilities for CLI output.
// Used by audit export (CAB-2022) and future trace query commands.
package redact

import (
	"net"
	"regexp"
	"strings"
)

var emailRegex = regexp.MustCompile(`[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}`)

// Email masks an email address: user@example.com → u***@e***.com
func Email(s string) string {
	return emailRegex.ReplaceAllStringFunc(s, maskEmail)
}

func maskEmail(email string) string {
	parts := strings.SplitN(email, "@", 2)
	if len(parts) != 2 {
		return email
	}
	local := parts[0]
	domain := parts[1]

	domainParts := strings.SplitN(domain, ".", 2)
	if len(domainParts) != 2 {
		return email
	}

	maskedLocal := string(local[0]) + "***"
	maskedDomain := string(domainParts[0][0]) + "***." + domainParts[1]
	return maskedLocal + "@" + maskedDomain
}

// IP masks an IP address.
// IPv4: 192.168.1.100 → 192.168.x.x
// IPv6: 2001:db8::1 → 2001:db8:x::x
func IP(s string) string {
	parsed := net.ParseIP(s)
	if parsed == nil {
		return s
	}

	if parsed.To4() != nil {
		// IPv4: keep first two octets
		parts := strings.SplitN(s, ".", 4)
		if len(parts) == 4 {
			return parts[0] + "." + parts[1] + ".x.x"
		}
		return s
	}

	// IPv6: keep first two groups, mask the rest
	expanded := parsed.String()
	parts := strings.SplitN(expanded, ":", 3)
	if len(parts) >= 2 {
		return parts[0] + ":" + parts[1] + ":x::x"
	}
	return s
}

// ipv4Regex matches IPv4 addresses in text
var ipv4Regex = regexp.MustCompile(`\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b`)

// AllIPs finds and masks all IP addresses in a string.
func AllIPs(s string) string {
	return ipv4Regex.ReplaceAllStringFunc(s, IP)
}

// All applies both email and IP redaction to a string.
func All(s string) string {
	s = Email(s)
	s = AllIPs(s)
	return s
}
