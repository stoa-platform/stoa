"""Private standard streams for the two long-lived Compose agent processes."""

from contextlib import contextmanager
import json
import select
import subprocess
import sys


def emit(message: dict) -> None:
    send(sys.stdout, message)


def send(pipe, message: dict) -> None:
    json.dump(message, pipe, separators=(",", ":"))
    pipe.write("\n")
    pipe.flush()


def receive(pipe, timeout: int = 45) -> dict:
    readable, _, _ = select.select([pipe], [], [], timeout)
    if not readable:
        raise RuntimeError("agent synchronization timed out")
    line = pipe.readline()
    if not line:
        raise RuntimeError("agent exited before completing synchronization")
    try:
        return json.loads(line)
    except ValueError:
        raise RuntimeError("invalid agent synchronization message") from None


@contextmanager
def agent_pair(script: str, mock_ip: str):
    def start(who: str) -> subprocess.Popen:
        return subprocess.Popen(
            [
                "docker", "compose", "exec", "-T", f"agent-{who}",
                "python3", "-B", script, who, mock_ip,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )

    with start("child") as child, start("parent") as parent:
        workers = (parent, child)
        try:
            yield parent, child
            for worker in workers:
                if worker.wait(timeout=15):
                    raise RuntimeError("an agent check failed")
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.terminate()
            for worker in workers:
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
