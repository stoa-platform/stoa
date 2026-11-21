#!/usr/bin/env python3
"""Tests unitaires locaux pour la preuve d'isolation Docker Compose du relais (sans Docker)."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
POC_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import relay_dock_smoke as dock  # noqa: E402
import relay_smoke as rs  # noqa: E402


def parse_compose_services(compose_text: str) -> dict[str, str]:
    """Découpe les blocs de services d'un fichier Compose simple (sans dépendance PyYAML)."""
    services: dict[str, list[str]] = {}
    in_services = False
    current: str | None = None
    for raw_line in compose_text.splitlines():
        if raw_line.startswith("services:"):
            in_services = True
            current = None
            continue
        if in_services and raw_line and not raw_line.startswith(" ") and not raw_line.startswith("#"):
            in_services = False
            current = None
            continue
        if not in_services:
            continue
        if raw_line.startswith("  ") and not raw_line.startswith("    ") and raw_line.strip().endswith(":"):
            current = raw_line.strip()[:-1]
            services[current] = []
        elif current is not None:
            services[current].append(raw_line)
    return {name: "\n".join(lines) for name, lines in services.items()}


class RelayDockComposeProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.compose_path = POC_DIR / "docker-compose.relay-dock.yml"
        self.compose_text = self.compose_path.read_text(encoding="utf-8")
        self.services = parse_compose_services(self.compose_text)
        self.runner_text = (SCRIPTS_DIR / "run_relay_dock.sh").read_text(encoding="utf-8")

    def test_dedicated_images_and_gateway_public_base_url(self) -> None:
        gw = self.services["stoa-gateway"]
        mock = self.services["upstream-mock"]
        self.assertIn("stoa-roles-relay-dock-local/gateway:dock", gw)
        self.assertIn("stoa-roles-relay-dock-local/mock:dock", mock)
        self.assertIn('STOA_POC_PUBLIC_BASE_URL: "http://127.0.0.1:8080"', gw)
        self.assertIn('STOA_POC_RELAY_ENROLLMENTS_FILE: "/etc/stoa/poc/relay-enrollments.json"', gw)
        self.assertNotIn("ports:", gw)

    def test_broker_and_agent_isolation_topology(self) -> None:
        broker = self.services["relay-broker"]
        parent = self.services["relay-parent"]
        child = self.services["relay-child"]

        self.assertIn('network_mode: "service:stoa-gateway"', broker)
        self.assertIn("relay-op:/run/stoa-relay/op", broker)
        self.assertIn("relay-parent-sock:/run/stoa-relay/parent", broker)
        self.assertIn("relay-child-sock:/run/stoa-relay/child", broker)

        for name, block, expected_vol, forbidden_vol in (
            ("relay-parent", parent, "relay-parent-sock:/run/stoa-relay/parent", "relay-child-sock"),
            ("relay-child", child, "relay-child-sock:/run/stoa-relay/child", "relay-parent-sock"),
        ):
            with self.subTest(service=name):
                self.assertIn('network_mode: "none"', block)
                self.assertIn('user: "1000:1000"', block)
                self.assertIn("read_only: true", block)
                self.assertIn("- ALL", block)
                self.assertIn("no-new-privileges:true", block)
                self.assertIn(expected_vol, block)
                self.assertNotIn("relay-op", block)
                self.assertNotIn(forbidden_vol, block)
                self.assertIn(":/usr/local/bin/stoactl:ro", block)
                self.assertNotIn("STOA_POC_BOOTSTRAP_SECRET", block)

        self.assertNotIn("docker.sock", self.compose_text)
        self.assertNotIn("privileged:", self.compose_text)

    def test_runner_has_no_static_secrets_and_explicit_scope(self) -> None:
        self.assertNotIn("refund-demo-backend-marker", self.runner_text)
        self.assertIn('COMPOSE_PROJECT_NAME="stoa-roles-dock-$suffix"', self.runner_text)
        self.assertIn("STOA_POC_STOACTL_LINUX_BIN", self.runner_text)
        self.assertIn("--prepare", self.runner_text)
        self.assertIn("Linux Compose", self.runner_text)
        self.assertIn("macOS", self.runner_text)
        self.assertIn("openssl rand -hex 24", self.runner_text)


class RelayDockSmokeUnitTest(unittest.TestCase):
    def test_prepare_dock_runtime_writes_hash_only_for_gateway(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dock.prepare_dock_runtime(root)

            proof_path = root / "op" / "proof"
            enroll_path = root / "gateway" / "relay-enrollments.json"
            self.assertEqual(stat.S_IMODE(os.lstat(proof_path).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.lstat(root / "op").st_mode), 0o700)

            proof = proof_path.read_text(encoding="ascii")
            self.assertEqual(len(proof), 64)
            expected_sha = hashlib.sha256(proof.encode("ascii")).hexdigest()

            enroll_raw = enroll_path.read_text(encoding="utf-8")
            self.assertNotIn(proof, enroll_raw)
            enroll = json.loads(enroll_raw)
            self.assertEqual(enroll["profiles"][0]["proof_sha256"], expected_sha)
            self.assertEqual(enroll["profiles"][0]["role"], rs.ROLE)

    def test_build_broker_config_sets_max_children_and_internal_loopback(self) -> None:
        cfg = dock.build_broker_config()
        self.assertEqual(cfg["gateway_url"], "http://127.0.0.1:8080")
        self.assertEqual(cfg["max_children"], 1)
        self.assertEqual(cfg["proof_file"], "/run/stoa-relay/op/proof")
        self.assertEqual(cfg["control_socket"], "/run/stoa-relay/op/control.sock")
        self.assertEqual(cfg["mcp_socket"], "/run/stoa-relay/parent/parent.sock")
        self.assertEqual(cfg["children_dir"], "/run/stoa-relay/child")

    def test_validate_private_ipv4_rejects_public_and_loopback(self) -> None:
        self.assertEqual(dock.validate_private_ipv4("192.0.2.3"), "192.0.2.3")
        self.assertEqual(dock.validate_private_ipv4("198.51.100.4"), "198.51.100.4")
        self.assertEqual(dock.validate_private_ipv4("203.0.113.2"), "203.0.113.2")
        non_private_samples = (
            str(ipaddress.IPv4Address(0xC0000301)),
            str(ipaddress.IPv4Address(0xC6336501)),
        )
        for bad in (*non_private_samples, "127.0.0.1", "169.254.169.254", "0.0.0.0", "upstream-mock"):
            with self.subTest(ip=bad):
                with self.assertRaises(rs.SmokeError):
                    dock.validate_private_ipv4(bad)

    def test_secret_leak_detection_and_clean_env(self) -> None:
        dock.assert_no_secrets_in_text(
            '{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"ok"}]}}',
            "clean",
        )
        for leaky in (
            "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhIn0.c2lnbmF0dXJl",
            "Authorization: DPoP abcdef0123456789abcdef",
            "-----BEGIN PRIVATE KEY-----",
            "x-api-key=secretvalue",
            "leaked=" + ("ab" * 24),
        ):
            with self.subTest(leaky=leaky[:24]):
                with self.assertRaises(rs.SmokeError):
                    dock.assert_no_secrets_in_text(leaky, "test")

        dock.check_clean_env({"PATH": "/usr/bin:/bin", "HOME": "/tmp/h", "LC_ALL": "C"}, "agent")
        dock.check_clean_env(
            {
                "PATH": "/usr/bin:/bin",
                "GPG_KEY": "7169605F62C745356BE063A4A4300A7E4B4327C3",
                "PYTHON_SHA256": "a" * 64,
            },
            "container",
            allow_image_vars=True,
        )
        with self.assertRaises(rs.SmokeError):
            dock.check_clean_env(
                {"PATH": "/usr/bin:/bin", "GPG_KEY": "7169605F62C745356BE063A4A4300A7E4B4327C3"},
                "shim",
                allow_image_vars=False,
            )
        for bad_env in (
            {"STOA_POC_BOOTSTRAP_SECRET": "abc"},
            {"UPSTREAM_API_KEY": "abc"},
            {"MY_TOKEN": "abc"},
        ):
            with self.subTest(env=list(bad_env)):
                with self.assertRaises(rs.SmokeError):
                    dock.check_clean_env(bad_env, "agent")

    def test_kernel_hardening_and_network_none_parsers(self) -> None:
        dock.check_proc_status_hardening("Name:\tpython3\nNoNewPrivs:\t1\nCapEff:\t0000000000000000\n", "ok")
        with self.assertRaises(rs.SmokeError):
            dock.check_proc_status_hardening("NoNewPrivs:\t1\nCapEff:\t0000000000000001\n", "caps")
        with self.assertRaises(rs.SmokeError):
            dock.check_proc_status_hardening("NoNewPrivs:\t0\nCapEff:\t0000000000000000\n", "nnp")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            net_ok = root / "net_ok"
            net_ok.mkdir()
            # Fichier sysfs (pas un périphérique) + pseudo-tunnels LinuxKit DOWN.
            (net_ok / "bonding_masters").write_text("", encoding="ascii")
            lo_dir = net_ok / "lo"
            lo_dir.mkdir()
            (lo_dir / "flags").write_text("0x9\n", encoding="ascii")
            (lo_dir / "operstate").write_text("unknown\n", encoding="ascii")
            for stub in ("erspan0", "gre0", "gretap0", "ip6_vti0", "ip6gre0", "ip6tnl0", "ip_vti0", "sit0", "tunl0"):
                d = net_ok / stub
                d.mkdir()
                (d / "flags").write_text("0x80\n", encoding="ascii")
                (d / "operstate").write_text("down\n", encoding="ascii")

            route_ok = root / "route_ok"
            route_ok.write_text("Iface\tDestination\tGateway\n", encoding="utf-8")
            fib_ok = root / "fib_ok"
            fib_ok.write_text(
                "Local:\n"
                "  +-- 127.0.0.0/8 2 0 2\n"
                "     |-- 127.0.0.0\n"
                "        /8 host LOCAL\n"
                "     |-- 127.0.0.1\n"
                "        /32 host LOCAL\n",
                encoding="utf-8",
            )
            inet6_ok = root / "if_inet6_ok"
            inet6_ok.write_text(
                "00000000000000000000000000000001 01 80 10 80 lo\n", encoding="utf-8"
            )
            route6_ok = root / "ipv6_route_ok"
            route6_ok.write_text(
                "00000000000000000000000000000001 80 00000000000000000000000000000000 00 "
                "00000000000000000000000000000000 00000100 00000000 00000000 00000001 lo\n",
                encoding="utf-8",
            )
            netns_link = root / "netns"
            os.symlink("net:[4026532999]", netns_link)

            common = dict(
                sys_net_dir=net_ok,
                proc_route_path=route_ok,
                proc_fib_trie_path=fib_ok,
                proc_if_inet6_path=inet6_ok,
                proc_ipv6_route_path=route6_ok,
                proc_netns_path=netns_link,
            )
            self.assertEqual(
                dock.check_network_none_kernel("ok", disallowed_netns=("net:[4026532000]",), **common),
                "net:[4026532999]",
            )

            # Namespace partagé refusé.
            with self.assertRaisesRegex(rs.SmokeError, "namespace réseau partagé"):
                dock.check_network_none_kernel("shared", disallowed_netns=("net:[4026532999]",), **common)

            # Périphérique non-lo UP ou opérationnel refusé.
            eth0 = net_ok / "eth0"
            eth0.mkdir()
            (eth0 / "flags").write_text("0x1003\n", encoding="ascii")
            (eth0 / "operstate").write_text("up\n", encoding="ascii")
            with self.assertRaisesRegex(rs.SmokeError, "eth0"):
                dock.check_network_none_kernel("eth0", **common)
            (eth0 / "flags").unlink()
            (eth0 / "operstate").unlink()
            eth0.rmdir()

            # Tunnel non-lo passé UP refusé.
            (net_ok / "gre0" / "flags").write_text("0x81\n", encoding="ascii")
            with self.assertRaisesRegex(rs.SmokeError, "gre0"):
                dock.check_network_none_kernel("gre0_up", **common)
            (net_ok / "gre0" / "flags").write_text("0x80\n", encoding="ascii")

            # Route IPv4 externe refusée.
            route_bad = root / "route_bad"
            route_bad.write_text(
                "Iface\tDestination\tGateway\neth0\t00000000\t010011AC\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(rs.SmokeError, "route IPv4 externe"):
                dock.check_network_none_kernel("route", **{**common, "proc_route_path": route_bad})

            # Adresse IPv4 non-loopback refusée.
            fib_bad = root / "fib_bad"
            fib_bad.write_text(
                "Local:\n  |-- 127.0.0.1\n     /32 host LOCAL\n  |-- 192.0.2.5\n     /32 host LOCAL\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(rs.SmokeError, r"192\.0\.2\.5"):
                dock.check_network_none_kernel("fib_bad", **{**common, "proc_fib_trie_path": fib_bad})

            # Adresse IPv6 non-loopback refusée.
            inet6_bad = root / "if_inet6_bad"
            inet6_bad.write_text(
                "fe800000000000000000000000000001 02 40 20 80 eth0\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(rs.SmokeError, "IPv6 non-loopback"):
                dock.check_network_none_kernel("inet6_bad", **{**common, "proc_if_inet6_path": inet6_bad})

            # Route IPv6 externe refusée.
            route6_bad = root / "ipv6_route_bad"
            route6_bad.write_text(
                "20010db8000000000000000000000000 20 00000000000000000000000000000000 00 "
                "fe800000000000000000000000000001 00000100 00000000 00000000 00000003 eth0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(rs.SmokeError, "route IPv6 externe"):
                dock.check_network_none_kernel("route6_bad", **{**common, "proc_ipv6_route_path": route6_bad})

    def test_verify_docker_inspect(self) -> None:
        def make_rec(cid: str, net_mode: str, *, networks: dict | None = None, mounts: list | None = None) -> dict:
            return {
                "Id": cid,
                "HostConfig": {
                    "NetworkMode": net_mode,
                    "ReadonlyRootfs": True,
                    "Privileged": False,
                    "CapDrop": ["ALL"],
                },
                "NetworkSettings": {
                    "IPAddress": "",
                    "GlobalIPv6Address": "",
                    "Networks": networks if networks is not None else {"none": {"IPAddress": "", "GlobalIPv6Address": ""}},
                },
                "Mounts": mounts or [],
            }

        gw_id = "1" * 64
        br_id = "2" * 64
        pa_id = "3" * 64
        ch_id = "4" * 64
        ok_records = [
            make_rec(gw_id, "bridge", networks={"mcp-net": {"IPAddress": "192.0.2.2"}}),
            make_rec(br_id, f"container:{gw_id}", networks={}),
            make_rec(pa_id, "none"),
            make_rec(ch_id, "none"),
        ]
        dock.verify_docker_inspect(ok_records, gateway_id=gw_id[:12], broker_id=br_id[:12], parent_id=pa_id[:12], child_id=ch_id[:12])

        bad_parent_net = list(ok_records)
        bad_parent_net[2] = make_rec(pa_id, "mcp-net", networks={"mcp-net": {"IPAddress": "192.0.2.4"}})
        with self.assertRaisesRegex(rs.SmokeError, "NetworkMode attendu 'none'"):
            dock.verify_docker_inspect(bad_parent_net, gateway_id=gw_id, broker_id=br_id, parent_id=pa_id, child_id=ch_id)

        bad_docker_sock = list(ok_records)
        bad_docker_sock[1] = make_rec(
            br_id, f"container:{gw_id}", networks={}, mounts=[{"Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock"}]
        )
        with self.assertRaisesRegex(rs.SmokeError, "docker.sock"):
            dock.verify_docker_inspect(bad_docker_sock, gateway_id=gw_id, broker_id=br_id, parent_id=pa_id, child_id=ch_id)

    def test_verify_upstream_stats(self) -> None:
        dock.verify_upstream_stats(dict(dock.EXPECTED_UPSTREAM_STATS))
        bad = dict(dock.EXPECTED_UPSTREAM_STATS, caller_auth_headers_seen=1)
        with self.assertRaises(rs.SmokeError):
            dock.verify_upstream_stats(bad)
        bad_count = dict(dock.EXPECTED_UPSTREAM_STATS, upstream_calls=3)
        with self.assertRaises(rs.SmokeError):
            dock.verify_upstream_stats(bad_count)

    def test_audited_shim_client_accepts_clean_and_rejects_stderr_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir(mode=0o700)

            clean_shim = root / "fake_stoactl_clean.py"
            clean_shim.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "for line in sys.stdin:\n"
                "    msg = json.loads(line)\n"
                "    if 'id' in msg:\n"
                "        print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'tools': []}}), flush=True)\n",
                encoding="utf-8",
            )
            os.chmod(clean_shim, 0o755)

            with dock.AuditedMcpStdioClient(str(clean_shim), "/tmp/fake.sock", home, "clean") as client:
                client.initialize()
                self.assertEqual(client.tools_list(), [])

            leaky_shim = root / "fake_stoactl_leaky.py"
            leaky_shim.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "sys.stderr.write('Authorization: DPoP eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhIn0.c2ln\\n')\n"
                "sys.stderr.flush()\n"
                "for line in sys.stdin:\n"
                "    msg = json.loads(line)\n"
                "    if 'id' in msg:\n"
                "        print(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': {}}), flush=True)\n",
                encoding="utf-8",
            )
            os.chmod(leaky_shim, 0o755)

            with self.assertRaises(rs.SmokeError):
                with dock.AuditedMcpStdioClient(str(leaky_shim), "/tmp/fake.sock", home, "leaky") as client:
                    client.initialize()


if __name__ == "__main__":
    unittest.main()
