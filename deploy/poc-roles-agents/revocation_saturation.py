#!/usr/bin/env python3
"""Run the revocation table saturation check with one process per agent."""

from contextlib import redirect_stdout
import os
import sys

from agent_harness import (
    DpopKey,
    run_revocation_saturation_child,
    run_revocation_saturation_parent,
)
from agent_pipes import agent_pair, emit, receive, send


def parent(gateway: str, mock_ip: str) -> None:
    child_jwk = receive(sys.stdin)["jwk"]
    with redirect_stdout(sys.stderr):
        child_token = run_revocation_saturation_parent(gateway, mock_ip, child_jwk)
    emit({"token": child_token})
    del child_token


def child(gateway: str, _mock_ip: str) -> None:
    dpop = DpopKey()
    emit({"jwk": dpop.jwk})
    token = receive(sys.stdin)["token"]
    with redirect_stdout(sys.stderr):
        run_revocation_saturation_child(gateway, dpop, token)
    emit({})


def orchestrate(mock_ip: str) -> None:
    with agent_pair("/app/revocation_saturation.py", mock_ip) as (parent_agent, child_agent):
        send(parent_agent.stdin, receive(child_agent.stdout))
        send(child_agent.stdin, receive(parent_agent.stdout))
        receive(child_agent.stdout)


if __name__ == "__main__":
    mode, mock_ip = sys.argv[1:]
    if mode == "host":
        orchestrate(mock_ip)
    else:
        {"parent": parent, "child": child}[mode](os.environ["STOA_GATEWAY_URL"], mock_ip)
