#!/usr/bin/env python3
"""Run the budget and restart checks with one process per agent."""

from contextlib import redirect_stdout
import os
import subprocess
import sys

from agent_harness import (
    DpopKey,
    run_jalon3_child_post_revoke,
    run_jalon3_child_use,
    run_jalon3_parent_phase1,
    run_jalon3_parent_revoke_and_race,
    run_jalon3_post_restart,
)
from agent_pipes import agent_pair, emit, receive, send


def parent(gateway: str, mock_ip: str) -> None:
    dpop = DpopKey()
    child_jwk = receive(sys.stdin)["jwk"]
    with redirect_stdout(sys.stderr):
        token_a, chain_a, child_token = run_jalon3_parent_phase1(
            gateway, mock_ip, dpop, child_jwk
        )
    emit({"token": child_token})
    del child_token

    receive(sys.stdin)
    with redirect_stdout(sys.stderr):
        token_c = run_jalon3_parent_revoke_and_race(gateway, dpop, token_a, chain_a)
    emit({})

    receive(sys.stdin, timeout=90)
    with redirect_stdout(sys.stderr):
        run_jalon3_post_restart(gateway, dpop, token_c)


def child(gateway: str, _mock_ip: str) -> None:
    dpop = DpopKey()
    emit({"jwk": dpop.jwk})
    token = receive(sys.stdin)["token"]
    with redirect_stdout(sys.stderr):
        run_jalon3_child_use(gateway, dpop, token)
    emit({})

    receive(sys.stdin)
    with redirect_stdout(sys.stderr):
        run_jalon3_child_post_revoke(gateway, dpop, token)
    emit({})


def restart_gateway() -> None:
    print("Restarting stoa-gateway for the in-memory token check", flush=True)
    subprocess.run(["docker", "compose", "restart", "stoa-gateway"], check=True, timeout=30)
    subprocess.run(
        [
            "docker", "compose", "exec", "-T", "stoa-gateway", "curl",
            "--fail", "--silent", "--retry", "30", "--retry-connrefused",
            "--retry-delay", "1", "--retry-max-time", "30", "--max-time", "2",
            "--output", "/dev/null", "http://127.0.0.1:8080/ready",
        ],
        check=True,
        timeout=40,
    )


def orchestrate(mock_ip: str) -> None:
    with agent_pair("/app/jalon3.py", mock_ip) as (parent_agent, child_agent):
        send(parent_agent.stdin, receive(child_agent.stdout))
        send(child_agent.stdin, receive(parent_agent.stdout))
        send(parent_agent.stdin, receive(child_agent.stdout))
        send(child_agent.stdin, receive(parent_agent.stdout))
        receive(child_agent.stdout)
        restart_gateway()
        send(parent_agent.stdin, {})


if __name__ == "__main__":
    mode, mock_ip = sys.argv[1:]
    if mode == "host":
        orchestrate(mock_ip)
    else:
        {"parent": parent, "child": child}[mode](os.environ["STOA_GATEWAY_URL"], mock_ip)
