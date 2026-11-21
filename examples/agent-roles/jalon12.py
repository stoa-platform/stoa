#!/usr/bin/env python3
"""Run the Jalon 1 and Jalon 2 agent checks with one process per agent."""

from contextlib import redirect_stdout
import os
import sys

from agent_harness import DpopKey, run_child, run_parent
from agent_pipes import agent_pair, emit, receive, send


def parent(gateway: str, mock_ip: str) -> None:
    child_jwk = receive(sys.stdin)["child_jwk"]
    with redirect_stdout(sys.stderr):
        parent_token, child_token = run_parent(gateway, mock_ip, child_jwk)
    payload = {"parent_token": parent_token}
    if child_token is not None:
        payload["child_token"] = child_token
    emit(payload)
    del parent_token, child_token, payload


def child(gateway: str, mock_ip: str) -> None:
    dpop = DpopKey()
    emit({"jwk": dpop.jwk})
    msg = receive(sys.stdin)
    parent_token = msg["parent_token"]
    child_token = msg.get("child_token")
    del msg
    with redirect_stdout(sys.stderr):
        run_child(gateway, mock_ip, dpop, parent_token, child_token)
    emit({})


def orchestrate(jalon: str, mock_ip: str) -> None:
    if jalon not in ("jalon1", "jalon2"):
        raise SystemExit(f"unknown jalon: {jalon}")
    with agent_pair("/app/jalon12.py", mock_ip) as (parent_agent, child_agent):
        child_hello = receive(child_agent.stdout)
        child_jwk = child_hello["jwk"] if jalon == "jalon2" else None
        send(parent_agent.stdin, {"child_jwk": child_jwk})
        send(child_agent.stdin, receive(parent_agent.stdout))
        receive(child_agent.stdout)


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "host":
        jalon, mock_ip = sys.argv[2], sys.argv[3]
        orchestrate(jalon, mock_ip)
    elif mode in ("parent", "child"):
        mock_ip = sys.argv[2]
        {"parent": parent, "child": child}[mode](os.environ["STOA_GATEWAY_URL"], mock_ip)
    else:
        raise SystemExit(f"unknown mode: {mode}")
