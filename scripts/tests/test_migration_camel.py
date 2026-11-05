# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""Synthetic constant-map flow reader and Camel XML contract tests."""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from scripts.migration_camel import generate, read_flow

SAMPLE = Path(__file__).parent / "fixtures/camel/constant.xml"
NS = {"c": "http://camel.apache.org/schema/spring"}


def test_sample_order_values_and_determinism():
    flow = read_flow(SAMPLE)
    output = generate(flow)
    assert output == generate(read_flow(SAMPLE))
    route = ET.fromstring(output).find("c:route", NS)
    assert route.attrib == {"id": "syntheticGreeting"}
    assert route[0].attrib == {"uri": "direct:syntheticGreeting"}
    assert [step.tag.split("}")[-1] for step in route] == [
        "from",
        "setHeader",
        "setBody",
        "setBody",
    ]
    assert route[1].attrib == {"name": "Content-Type"}
    assert [step[0].text for step in route[1:]] == [
        "text/plain",
        "Hello & welcome",
        "  Synthetic <reply>  ",
    ]
    assert all(step[0].attrib == {"trim": "false"} for step in route[1:])


@pytest.mark.parametrize(
    "source",
    [
        "<FLOW>",
        '<FLOW NAME="x"><BRANCH /></FLOW>',
        '<FLOW NAME="x"><SEQUENCE><INVOKE SERVICE="foo" /></SEQUENCE></FLOW>',
        '<FLOW NAME="x"><SEQUENCE /></FLOW>',
        '<FLOW NAME="x"><SEQUENCE /><SEQUENCE /></FLOW>',
        '<FLOW NAME="x" UNKNOWN="yes"><SEQUENCE /></FLOW>',
        '<FLOW NAME="../x"><SEQUENCE /></FLOW>',
        '<FLOW NAME="x"><SEQUENCE><MAP><MAPSET FIELD="body" /></MAP></SEQUENCE></FLOW>',
        '<FLOW NAME="x"><SEQUENCE><MAP><MAPSET FIELD="other" VALUE="x" /></MAP></SEQUENCE></FLOW>',
        '<FLOW NAME="x"><SEQUENCE>ignored<MAP /></SEQUENCE></FLOW>',
        '<!DOCTYPE FLOW [<!ENTITY x "boom">]><FLOW NAME="x">&x;</FLOW>',
        '<FLOW xmlns="unexpected" NAME="x"><SEQUENCE /></FLOW>',
        '<FLOW NAME="x"><SEQUENCE><MAP><MAPSET FIELD="body" VALUE="{{secret}}" /></MAP></SEQUENCE></FLOW>',
        '<FLOW NAME="x"><SEQUENCE><MAP><MAPSET FIELD="body" VALUE="resource:file:x" /></MAP></SEQUENCE></FLOW>',
    ],
)
def test_rejects_unsupported_or_unsafe_input(tmp_path, source):
    path = tmp_path / "flow.xml"
    path.write_text(source)
    with pytest.raises(ValueError):
        read_flow(path)


def test_empty_constant_and_multiple_assignments(tmp_path):
    path = tmp_path / "flow.xml"
    path.write_text(
        '<FLOW NAME="empty"><SEQUENCE><MAP>'
        '<MAPSET FIELD="body" VALUE="" />'
        '<MAPSET FIELD="header.X-Test" VALUE="ok" />'
        "</MAP></SEQUENCE></FLOW>"
    )
    route = ET.fromstring(generate(read_flow(path))).find("c:route", NS)
    assert len(route) == 3
    assert route[1][0].text is None


@pytest.mark.parametrize("field,step", [("body", "setBody"), ("header.X-Test", "setHeader")])
@pytest.mark.parametrize("encoded,expected", [("a&#13;b", "a\rb"), ("a&#13;&#10;b", "a\r\nb")])
def test_carriage_returns_survive_xml_round_trip(tmp_path, field, step, encoded, expected):
    path = tmp_path / "flow.xml"
    path.write_text(
        '<FLOW NAME="lineEndings"><SEQUENCE><MAP>'
        f'<MAPSET FIELD="{field}" VALUE="{encoded}" />'
        "</MAP></SEQUENCE></FLOW>"
    )
    flow = read_flow(path)
    assert flow.assignments == ((field, expected),)
    output = generate(flow)
    constant = ET.fromstring(output).find(f"c:route/c:{step}/c:constant", NS)
    assert constant.text == expected
    assert "&#13;" in output
    assert "\r" not in output


def test_size_limit(tmp_path):
    path = tmp_path / "large.xml"
    path.write_bytes(b" " * 1_000_001)
    with pytest.raises(ValueError, match="size"):
        read_flow(path)


def test_cli_success_and_failure(tmp_path):
    script = Path(__file__).parents[1] / "migration_camel.py"
    result = subprocess.run(
        [sys.executable, str(script), str(SAMPLE)], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout == generate(read_flow(SAMPLE)) + "\n"
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path / "missing")], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert not result.stdout
    assert "error:" in result.stderr
