# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""Translate a strict synthetic FLOW/SEQUENCE/MAP profile into Camel XML."""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
LIMIT = 1_000_000


@dataclass(frozen=True)
class Flow:
    name: str
    assignments: tuple[tuple[str, str], ...]


def _shape(node: ET.Element, tag: str, attrs: set[str]) -> None:
    if node.tag != tag or set(node.attrib) != attrs:
        raise ValueError(f"Unsupported element or attributes: {node.tag}; expected {tag}")
    if (node.text or "").strip() or (node.tail or "").strip():
        raise ValueError("Mixed XML content is unsupported")


def read_flow(path: Path) -> Flow:
    """Read only the documented synthetic profile; never silently drop a step."""
    with path.open("rb") as source:
        data = source.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Flow exceeds size limit")
    # UTF-8 only: reject DTDs before parsing, including entity expansion.
    text = data.decode("utf-8-sig")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("DTD and entities are unsupported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(f"Invalid flow XML: {error}") from error
    _shape(root, "FLOW", {"NAME"})
    name = root.attrib["NAME"]
    if not NAME.fullmatch(name):
        raise ValueError("Invalid flow name")
    if len(root) != 1:
        raise ValueError("Expected one SEQUENCE")
    sequence = root[0]
    _shape(sequence, "SEQUENCE", set())
    assignments = []
    for mapping in sequence:
        _shape(mapping, "MAP", set())
        if not len(mapping):
            raise ValueError("Empty MAP is unsupported")
        for assignment in mapping:
            _shape(assignment, "MAPSET", {"FIELD", "VALUE"})
            if len(assignment):
                raise ValueError("Nested MAPSET is unsupported")
            field, value = assignment.attrib["FIELD"], assignment.attrib["VALUE"]
            if field != "body" and not (field.startswith("header.") and NAME.fullmatch(field[7:])):
                raise ValueError(f"Unsupported field: {field}")
            # Camel resolves property placeholders and resource constants at load time.
            if "{{" in value or value.startswith("resource:"):
                raise ValueError("Camel placeholders and resource constants are unsupported")
            assignments.append((field, value))
    if not assignments:
        raise ValueError("Empty SEQUENCE is unsupported")
    return Flow(name, tuple(assignments))


def generate(flow: Flow) -> str:
    """Generate ordered string assignments, preserving whitespace in constants."""
    routes = ET.Element("routes", xmlns="http://camel.apache.org/schema/spring")
    route = ET.SubElement(routes, "route", id=flow.name)
    ET.SubElement(route, "from", uri=f"direct:{flow.name}")
    for field, value in flow.assignments:
        step = (
            ET.SubElement(route, "setBody")
            if field == "body"
            else ET.SubElement(route, "setHeader", name=field[7:])
        )
        ET.SubElement(step, "constant", trim="false").text = value
    ET.indent(routes, space="  ")
    # XML parsers normalize literal CR/CRLF; character references preserve CR.
    return ET.tostring(routes, encoding="unicode").replace("\r", "&#13;")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flow", type=Path)
    args = parser.parse_args()
    try:
        output = generate(read_flow(args.flow))
    except (OSError, ValueError, ET.ParseError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
