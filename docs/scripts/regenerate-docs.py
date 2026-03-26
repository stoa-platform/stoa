#!/usr/bin/env python3
"""regenerate-docs.py — Generate DEPENDENCIES.md and SCENARIOS.md from stoa-impact.db.

These markdown files are VIEWS, not the source of truth.
Edit populate-db.py to change the data, then run: python3 docs/scripts/populate-db.py

Usage: python3 docs/scripts/regenerate-docs.py
"""

import sqlite3
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "..", "stoa-impact.db")
DEPS_PATH = os.path.join(SCRIPT_DIR, "..", "DEPENDENCIES.md")
SCENARIOS_PATH = os.path.join(SCRIPT_DIR, "..", "SCENARIOS.md")


def generate_dependencies(conn: sqlite3.Connection) -> str:
    """Generate DEPENDENCIES.md content."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "<!-- AUTO-GENERATED from stoa-impact.db — DO NOT EDIT MANUALLY -->",
        "<!-- Regenerate: python3 docs/scripts/regenerate-docs.py -->",
        f"<!-- Last generated: {now} -->",
        "",
        "# STOA Platform — Dependency Map",
        "",
    ]

    # Summary stats
    total_c = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    typed_c = conn.execute("SELECT COUNT(*) FROM contracts WHERE typed = 1").fetchone()[0]
    untyped_c = total_c - typed_c
    active = conn.execute("SELECT COUNT(*) FROM components WHERE status = 'active'").fetchone()[0]
    open_risks = conn.execute("SELECT COUNT(*) FROM risks WHERE status = 'open'").fetchone()[0]
    crit_risks = conn.execute("SELECT COUNT(*) FROM risks WHERE severity = 'CRITICAL' AND status = 'open'").fetchone()[0]

    lines.append(f"> **{active}** active components | **{total_c}** contracts ({typed_c} typed, **{untyped_c} untyped**) | **{open_risks}** open risks ({crit_risks} CRITICAL)")
    lines.append("")

    # Components section
    lines.append("## Components")
    lines.append("")

    components = conn.execute(
        "SELECT id, name, type, tech_stack, repo_path, status, description FROM components ORDER BY type, name"
    ).fetchall()

    for comp_id, name, ctype, stack, path, status, desc in components:
        status_badge = "" if status == "active" else f" **[{status.upper()}]**"
        path_str = f"`{path}`" if path else "N/A"
        lines.append(f"### {name} (`{comp_id}`){status_badge}")
        lines.append(f"- **Type**: {ctype} | **Stack**: {stack} | **Path**: {path_str}")
        lines.append(f"- {desc}")

        # Outgoing contracts
        outgoing = conn.execute(
            "SELECT id, target_component, type, contract_ref, typed FROM contracts WHERE source_component = ? ORDER BY target_component",
            (comp_id,),
        ).fetchall()
        if outgoing:
            lines.append(f"- **Outgoing** ({len(outgoing)} contracts):")
            for cid, target, ctype_c, ref, typed in outgoing:
                typed_mark = "" if typed else " **UNTYPED**"
                lines.append(f"  - `{cid}` → `{target}` ({ctype_c}): `{ref}`{typed_mark}")

        # Incoming contracts
        incoming = conn.execute(
            "SELECT id, source_component, type, contract_ref, typed FROM contracts WHERE target_component = ? ORDER BY source_component",
            (comp_id,),
        ).fetchall()
        if incoming:
            lines.append(f"- **Incoming** ({len(incoming)} contracts):")
            for cid, source, ctype_c, ref, typed in incoming:
                typed_mark = "" if typed else " **UNTYPED**"
                lines.append(f"  - `{cid}` ← `{source}` ({ctype_c}): `{ref}`{typed_mark}")

        # Scenarios involving this component
        scenarios = conn.execute(
            """SELECT DISTINCT s.id, s.name, s.priority, s.test_level
            FROM scenarios s
            JOIN scenario_steps ss ON s.id = ss.scenario_id
            WHERE ss.component_id = ?
            ORDER BY s.priority, s.name""",
            (comp_id,),
        ).fetchall()
        if scenarios:
            scenario_list = [f"{sid} ({sprio}, {tlevel})" for sid, sname, sprio, tlevel in scenarios]
            lines.append(f"- **Scenarios**: {', '.join(scenario_list)}")

        lines.append("")

    # Dependency matrix
    lines.append("## Dependency Matrix")
    lines.append("")

    active_ids = [c[0] for c in components if c[5] == "active"]
    matrix = {}
    for row in conn.execute("SELECT source_component, target_component FROM contracts").fetchall():
        matrix[(row[0], row[1])] = True

    header = "| Source \\ Target |"
    separator = "|---|"
    for cid in active_ids:
        short = cid[:6]
        header += f" {short} |"
        separator += ":---:|"
    lines.append(header)
    lines.append(separator)

    for src in active_ids:
        row = f"| **{src[:14]}** |"
        for tgt in active_ids:
            if src == tgt:
                row += " - |"
            elif (src, tgt) in matrix:
                row += " x |"
            else:
                row += "   |"
        lines.append(row)

    lines.append("")

    # Untyped contracts alert
    untyped = conn.execute(
        "SELECT id, contract_ref, source_component, target_component, type FROM untyped_contracts"
    ).fetchall()
    if untyped:
        lines.append("## Untyped Contracts (Risk Alert)")
        lines.append("")
        lines.append(f"**{len(untyped)} contracts** have no formal schema enforcement:")
        lines.append("")
        lines.append("| ID | Source → Target | Type | Reference |")
        lines.append("|---|---|---|---|")
        for cid, ref, src, tgt, ctype in untyped:
            lines.append(f"| `{cid}` | {src} → {tgt} | {ctype} | `{ref}` |")
        lines.append("")

    # Risk summary
    risks = conn.execute(
        "SELECT id, severity, title, status, ticket_ref FROM risks ORDER BY "
        "CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END"
    ).fetchall()
    if risks:
        lines.append("## Risk Summary")
        lines.append("")
        lines.append("| ID | Severity | Title | Status | Ticket |")
        lines.append("|---|---|---|---|---|")
        for rid, sev, title, status, ticket in risks:
            ticket_str = ticket if ticket else "—"
            sev_mark = f"**{sev}**" if sev in ("CRITICAL", "HIGH") else sev
            lines.append(f"| {rid} | {sev_mark} | {title} | {status} | {ticket_str} |")
        lines.append("")

    # Contract inventory
    lines.append("## Contract Inventory")
    lines.append("")
    lines.append("| ID | Source | Target | Type | Reference | Typed |")
    lines.append("|---|---|---|---|---|---|")
    for row in conn.execute(
        "SELECT id, source_component, target_component, type, contract_ref, typed FROM contracts ORDER BY id"
    ).fetchall():
        typed_str = "Yes" if row[5] else "**No**"
        lines.append(f"| `{row[0]}` | {row[1]} | {row[2]} | {row[3]} | `{row[4]}` | {typed_str} |")

    lines.append("")
    return "\n".join(lines)


def generate_scenarios(conn: sqlite3.Connection) -> str:
    """Generate SCENARIOS.md content."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "<!-- AUTO-GENERATED from stoa-impact.db — DO NOT EDIT MANUALLY -->",
        "<!-- Regenerate: python3 docs/scripts/regenerate-docs.py -->",
        f"<!-- Last generated: {now} -->",
        "",
        "# STOA Platform — End-to-End Scenarios",
        "",
    ]

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0]
    in_ci = conn.execute("SELECT COUNT(*) FROM scenarios WHERE test_in_ci = 1").fetchone()[0]
    p0_untested = conn.execute(
        "SELECT COUNT(*) FROM scenarios WHERE priority = 'P0' AND test_in_ci = 0"
    ).fetchone()[0]

    lines.append(f"> **{total}** scenarios | **{in_ci}** in CI | **{p0_untested} P0 untested**")
    lines.append("")

    scenarios = conn.execute(
        "SELECT id, name, description, actor, priority, test_level, test_in_ci FROM scenarios ORDER BY priority, id"
    ).fetchall()

    current_priority = None
    for sid, name, desc, actor, priority, test_level, test_in_ci in scenarios:
        if priority != current_priority:
            current_priority = priority
            prio_labels = {"P0": "Critical", "P1": "Important", "P2": "Nice-to-have"}
            lines.append(f"## {priority} — {prio_labels.get(priority, priority)}")
            lines.append("")

        ci_badge = "CI" if test_in_ci else "NO CI"
        lines.append(f"### {sid}: {name}")
        lines.append(f"**Actor**: {actor} | **Test**: {test_level} | **{ci_badge}**  ")
        lines.append(f"{desc}")
        lines.append("")

        # Steps
        steps = conn.execute(
            """SELECT ss.step_order, ss.component_id, ss.action, ss.contract_id, ss.expected_result
            FROM scenario_steps ss
            WHERE ss.scenario_id = ?
            ORDER BY ss.step_order""",
            (sid,),
        ).fetchall()

        lines.append("| # | Component | Action | Contract | Expected Result |")
        lines.append("|---|---|---|---|---|")
        for order, comp, action, contract, result in steps:
            contract_str = f"`{contract}`" if contract else "—"
            lines.append(f"| {order} | `{comp}` | {action} | {contract_str} | {result} |")

        # Contracts traversed
        contracts = conn.execute(
            """SELECT DISTINCT c.id, c.contract_ref, c.typed
            FROM scenario_steps ss
            JOIN contracts c ON ss.contract_id = c.id
            WHERE ss.scenario_id = ?
            ORDER BY c.id""",
            (sid,),
        ).fetchall()
        if contracts:
            contract_list = []
            for cid, ref, typed in contracts:
                typed_mark = "" if typed else " **UNTYPED**"
                contract_list.append(f"`{cid}`{typed_mark}")
            lines.append("")
            lines.append(f"**Contracts traversed**: {', '.join(contract_list)}")

        lines.append("")

    # Impact summary
    lines.append("## Impact Summary")
    lines.append("")
    lines.append("Components by scenario count (most critical first):")
    lines.append("")

    comp_counts = conn.execute(
        """SELECT ss.component_id, COUNT(DISTINCT ss.scenario_id) as cnt
        FROM scenario_steps ss
        GROUP BY ss.component_id
        ORDER BY cnt DESC"""
    ).fetchall()
    for comp, count in comp_counts:
        lines.append(f"- **{comp}**: {count} scenarios")

    lines.append("")

    # Untested P0 alert
    untested_p0 = conn.execute(
        "SELECT id, name FROM scenarios WHERE priority = 'P0' AND test_in_ci = 0"
    ).fetchall()
    if untested_p0:
        lines.append("## P0 Scenarios Without CI Coverage")
        lines.append("")
        for sid, name in untested_p0:
            lines.append(f"- **{sid}**: {name}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run: python3 docs/scripts/populate-db.py")
        return

    conn = sqlite3.connect(DB_PATH)

    # Generate DEPENDENCIES.md
    deps_content = generate_dependencies(conn)
    with open(DEPS_PATH, "w") as f:
        f.write(deps_content)
    print(f"Generated {DEPS_PATH}")

    # Generate SCENARIOS.md
    scenarios_content = generate_scenarios(conn)
    with open(SCENARIOS_PATH, "w") as f:
        f.write(scenarios_content)
    print(f"Generated {SCENARIOS_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
