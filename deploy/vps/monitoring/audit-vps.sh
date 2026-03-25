#!/usr/bin/env bash
# Collect system audit data from a single VPS (runs remotely via SSH)
# Output: structured key=value pairs, consumed by run-audit.sh
set -euo pipefail

echo "=== SYSTEM ==="
echo "hostname=$(hostname -f 2>/dev/null || hostname)"
echo "kernel=$(uname -r)"
echo "os=$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || uname -s)"
echo "arch=$(uname -m)"
echo "uptime_days=$(awk '{printf "%.1f", $1/86400}' /proc/uptime 2>/dev/null || echo "N/A")"
echo "load=$(cat /proc/loadavg 2>/dev/null | cut -d' ' -f1-3 || echo "N/A")"
echo "cpus=$(nproc 2>/dev/null || echo "?")"

echo "=== MEMORY ==="
if command -v free &>/dev/null; then
  free -m | awk '/^Mem:/ {printf "ram_total=%dMB\nram_used=%dMB\nram_pct=%.0f%%\n", $2, $3, $3/$2*100}'
  free -m | awk '/^Swap:/ {if($2>0) printf "swap_total=%dMB\nswap_used=%dMB\n", $2, $3; else print "swap=none"}'
else
  echo "ram_total=N/A"
fi

echo "=== DISK ==="
df -h / | awk 'NR==2 {printf "disk_total=%s\ndisk_used=%s\ndisk_avail=%s\ndisk_pct=%s\n", $2, $3, $4, $5}'
# Flag if any mount > 85%
df -h --output=pcent,target 2>/dev/null | tail -n+2 | while read pct mount; do
  num=${pct%%%}
  if [[ "$num" =~ ^[0-9]+$ ]] && [[ "$num" -ge 85 ]]; then
    echo "disk_warn=${mount} at ${pct}"
  fi
done

echo "=== DOCKER ==="
if command -v docker &>/dev/null; then
  echo "docker_version=$(docker --version 2>/dev/null | grep -oP '[\d.]+' | head -1)"
  echo "docker_containers=$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')"
  echo "docker_images=$(docker images -q 2>/dev/null | wc -l | tr -d ' ')"
  # Docker disk usage (compact)
  docker_disk=$(docker system df --format '{{.Type}}\t{{.Size}}\t{{.Reclaimable}}' 2>/dev/null || echo "")
  if [[ -n "$docker_disk" ]]; then
    echo "docker_disk_raw<<EOF"
    echo "$docker_disk"
    echo "EOF"
  fi
  # Running containers list
  echo "docker_ps<<EOF"
  docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null || echo "none"
  echo "EOF"
else
  echo "docker=not_installed"
fi

echo "=== SERVICES ==="
# Key systemd services
for svc in node_exporter push-metrics.timer vault vault-agent hegemon-agent docker nginx caddy; do
  if systemctl is-enabled "$svc" &>/dev/null 2>&1; then
    state=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    echo "svc_${svc//-/_}=${state}"
  fi
done

echo "=== SECURITY ==="
# Unattended upgrades
if dpkg -l unattended-upgrades &>/dev/null 2>&1; then
  echo "unattended_upgrades=installed"
else
  echo "unattended_upgrades=missing"
fi
# Fail2ban
if systemctl is-active fail2ban &>/dev/null 2>&1; then
  echo "fail2ban=active"
elif command -v fail2ban-client &>/dev/null; then
  echo "fail2ban=installed_inactive"
else
  echo "fail2ban=missing"
fi
# SSH config checks
echo "ssh_root_login=$(grep -E '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' || echo "unknown")"
echo "ssh_password_auth=$(grep -E '^PasswordAuthentication' /etc/ssh/sshd_config 2>/dev/null | awk '{print $2}' || echo "unknown")"
# Firewall
if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "active"; then
  echo "firewall=ufw_active"
elif command -v iptables &>/dev/null; then
  rules=$(iptables -L -n 2>/dev/null | grep -c -v '^Chain\|^target\|^$' || echo "0")
  echo "firewall=iptables_${rules}_rules"
else
  echo "firewall=none"
fi

echo "=== UPDATES ==="
# Pending security updates (Debian/Ubuntu)
if command -v apt-get &>/dev/null; then
  updates=$(apt-get -s upgrade 2>/dev/null | grep -c '^Inst' || echo "0")
  security=$(apt-get -s upgrade 2>/dev/null | grep -c '/security' || echo "0")
  echo "pending_updates=${updates}"
  echo "pending_security=${security}"
fi
# Last apt update
if [[ -f /var/lib/apt/periodic/update-success-stamp ]]; then
  last=$(stat -c %Y /var/lib/apt/periodic/update-success-stamp 2>/dev/null || echo "0")
  now=$(date +%s)
  days=$(( (now - last) / 86400 ))
  echo "apt_last_update=${days}_days_ago"
elif [[ -f /var/cache/apt/pkgcache.bin ]]; then
  last=$(stat -c %Y /var/cache/apt/pkgcache.bin 2>/dev/null || echo "0")
  now=$(date +%s)
  days=$(( (now - last) / 86400 ))
  echo "apt_cache_age=${days}_days"
fi

echo "=== NETWORK ==="
echo "listening_ports=$(ss -tlnp 2>/dev/null | tail -n+2 | wc -l | tr -d ' ')"
# Public-facing ports (non-localhost)
ss -tlnp 2>/dev/null | tail -n+2 | awk '$4 !~ /^127\./ && $4 !~ /^\[::1\]/ {print $4}' | sort -u | while read addr; do
  echo "open_port=${addr}"
done

echo "=== END ==="
