# Demo Day Countdown — 24 February 2026

> **Ticket**: CAB-1075
> **Rule**: Zero surprise. Plan A, B, C ready.
> **Gate**: Cedric says "Go, t'es pret"

---

## Demo Assets Inventory

| Asset | File | Status |
|-------|------|--------|
| Technical script (8 acts, 20 min) | `DEMO-SCRIPT.md` | Done |
| Narrative + speaker notes (6 acts) | `DEMO-NARRATIVE.md` | Done |
| 5-minute Design Partner pitch | `DEMO-PITCH-5MIN.md` | Done |
| Slide deck (10 Marp slides) | `DEMO-SLIDES.md` | Done |
| Slide deck PDF export | `DEMO-SLIDES.pdf` | Done |
| Slide deck PPTX export | `DEMO-SLIDES.pptx` | Done |
| Pre-flight checklist | `DEMO-CHECKLIST.md` | Done |
| Fallback procedures | `DEMO-PLAN-B.md` | Done |
| Dry-run reports | `DRY-RUN-1.md` | Done |
| Automated smoke test | `scripts/demo/demo-dry-run.sh` | Done (23/23 GO) |
| Backup video | _To record_ | **Pending** |
| Screenshots backup | _To capture_ | **Pending** |

---

## J-7: Sunday 16 Feb — Code Freeze

### Freeze Rules

- **PROD freeze** in effect since Sunday 15 Feb 18h (Cycle 7 close)
- No code changes to `main` that affect deployed components
- Allowed: docs-only commits (`.md`, `.claude/`), state file updates
- Forbidden: any change to `control-plane-api/`, `control-plane-ui/`, `portal/`, `stoa-gateway/`, `charts/`

### Verify Freeze

```bash
# Check last deploy-triggering commit on main
git log --oneline main -- control-plane-api/ control-plane-ui/ portal/ stoa-gateway/ | head -3
# Must be older than Feb 15 18h
```

---

## J-5: Wednesday 19 Feb — Rehearsal #1

### Infra Health Check (Production)

```bash
export KUBECONFIG=~/.kube/config-stoa-ovh

# All pods running
kubectl get pods -n stoa-system -o wide
kubectl get pods -n monitoring -o wide

# All HTTPS endpoints respond
for svc in console portal api mcp auth; do
  printf "%-12s " "${svc}.gostoa.dev:"
  curl -sI "https://${svc}.gostoa.dev" -o /dev/null -w "%{http_code}\n" --max-time 5
done

# Grafana
curl -sI "https://console.gostoa.dev/grafana" -o /dev/null -w "grafana: %{http_code}\n" --max-time 5

# Status page
curl -sI "https://status.gostoa.dev" -o /dev/null -w "status: %{http_code}\n" --max-time 5
```

- [ ] All services respond 200
- [ ] No pod in CrashLoopBackOff or Pending
- [ ] ArgoCD: all apps Synced + Healthy

### Automated Smoke Test

```bash
./scripts/demo/demo-dry-run.sh
```

- [ ] Result: **GO** (23/23 PASS)
- [ ] Execution time: < 10s

### Timed Rehearsal (Solo)

- [ ] Run through DEMO-NARRATIVE.md (6 acts)
- [ ] Timer: **must finish in 20 min** (allow 5 min buffer for demo day nerves)
- [ ] Note any friction points → fix if < 30 min work, defer otherwise

### Checklist

- [ ] Code freeze verified (no deploy-triggering commits since Feb 15)
- [ ] Infra health: all pods UP, all HTTPS endpoints 200
- [ ] Smoke test: 23/23 GO
- [ ] Solo rehearsal completed (timer < 20 min)
- [ ] Frictions noted and triaged

---

## J-3: Friday 21 Feb — Dry Run with Witness

### Cedric Witness Protocol

**Objective**: Cedric observes a full run and validates "pret".

**Setup**:
1. Share screen (Zoom/Meet or in-person)
2. Cedric has a copy of DEMO-NARRATIVE.md open for reference
3. Cedric uses the scorecard below to rate each section

**Scorecard** (Cedric fills this):

| Section | Time Target | Actual Time | Smooth? | Friction Notes |
|---------|------------|-------------|---------|----------------|
| Hook | 0:00-2:00 | ___:___ | Y / N | |
| Act 1: Console | 2:00-5:00 | ___:___ | Y / N | |
| Act 2: Portal | 5:00-8:00 | ___:___ | Y / N | |
| Act 3: Gateway + mTLS | 8:00-13:00 | ___:___ | Y / N | |
| Act 4: Observability | 13:00-14:00 | ___:___ | Y / N | |
| Act 5: MCP Bridge | 14:00-16:00 | ___:___ | Y / N | |
| Act 6: GitOps + Close | 16:00-20:00 | ___:___ | Y / N | |
| **Total** | **20:00** | **___:___** | | |

**Verdict**: [ ] GO / [ ] NO-GO

**If NO-GO**: list blockers → fix Friday evening → re-run Saturday if needed.

### Checklist

- [ ] Smoke test re-run: 23/23 GO
- [ ] Full rehearsal with Cedric (timed)
- [ ] Cedric scorecard completed
- [ ] Cedric verdict: **GO**
- [ ] Any friction < 30 min: fixed
- [ ] Any friction > 30 min: documented as known limitation

---

## J-1: Sunday 23 Feb — Final Check

### Video Backup Recording

If not already recorded:

```bash
# macOS screen recording
# 1. Open QuickTime Player → File → New Screen Recording
# 2. Set up all 5 tabs (Console, Portal, Terminal, Grafana, Slides)
# 3. Run through DEMO-PITCH-5MIN.md (condensed 5 min version)
# 4. Save to ~/Desktop/demo-backup-2026-02-23.mov
# 5. Also export as .mp4 for maximum compatibility
```

- [ ] Video recorded (clean run, no mistakes)
- [ ] Video saved locally (not cloud-only)
- [ ] Video plays without internet connection
- [ ] Video accessible from both primary and backup laptop

### Asset Verification

- [ ] DEMO-SLIDES.pdf on desktop (offline access)
- [ ] DEMO-SLIDES.pptx on desktop (editable backup)
- [ ] DEMO-NARRATIVE.md printed or on phone (speaker notes backup)
- [ ] DEMO-PITCH-5MIN.md printed (5-min version if time is cut)

### Credentials Verification

```bash
# Verify demo credentials still work
# Console (halliday)
curl -s -X POST "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=control-plane-ui&username=halliday&password=readyplayerone" \
  | python3 -c "import sys,json; t=json.load(sys.stdin); print('OK' if 'access_token' in t else 'FAIL')"

# Portal (art3mis)
curl -s -X POST "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=stoa-portal&username=art3mis&password=samantha2045" \
  | python3 -c "import sys,json; t=json.load(sys.stdin); print('OK' if 'access_token' in t else 'FAIL')"
```

- [ ] halliday login: OK
- [ ] art3mis login: OK
- [ ] Grafana admin login: OK

### Pre-Cache Tokens

```bash
# Generate and save tokens for Plan B (if auth breaks during demo)
HALLIDAY_TOKEN=$(curl -s -X POST "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=control-plane-ui&username=halliday&password=readyplayerone" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

ARTMIS_TOKEN=$(curl -s -X POST "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=stoa-portal&username=art3mis&password=samantha2045" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Save to a local file (gitignored, ephemeral)
cat > /tmp/demo-tokens.env << ENVEOF
HALLIDAY_TOKEN=${HALLIDAY_TOKEN}
ARTMIS_TOKEN=${ARTMIS_TOKEN}
ENVEOF

echo "Tokens cached in /tmp/demo-tokens.env (valid ~5 min)"
```

- [ ] Tokens cached (refresh again T-30 min before demo)

### Laptop Preparation

- [ ] macOS Do Not Disturb: ON
- [ ] Browser notifications: OFF
- [ ] Personal tabs: closed
- [ ] History/bookmarks bar: hidden
- [ ] Terminal font: 18pt
- [ ] Dark mode: OFF (projector readability)
- [ ] Battery: 100% + charger packed
- [ ] Backup laptop: charged, slides copied

### Checklist

- [ ] Video backup recorded and tested offline
- [ ] All assets on local disk (slides, narrative, pitch)
- [ ] Credentials verified (halliday + art3mis + grafana)
- [ ] Tokens pre-cached
- [ ] Laptop clean and prepared
- [ ] Backup laptop ready

---

## J-Day: Monday 24 Feb — Showtime

### T-60 min: Travel

- [ ] Primary laptop + charger
- [ ] Backup laptop + charger
- [ ] Phone (hotspot backup)
- [ ] USB-C / HDMI adapter (for projector)
- [ ] Printed DEMO-NARRATIVE.md (speaker notes)

### T-30 min: Setup

```bash
# 1. Run smoke test
./scripts/demo/demo-dry-run.sh
# Expected: GO (23/23)

# 2. Refresh cached tokens
# (tokens from J-1 are expired, generate fresh ones)
source /tmp/demo-tokens.env 2>/dev/null  # old ones
# Re-run the token caching script from J-1 section above
```

- [ ] Smoke test: **GO**
- [ ] Fresh tokens cached
- [ ] Wifi connected and tested
- [ ] Hotspot tested (backup)
- [ ] Projector/screen connected and working
- [ ] Audio tested (if remote presentation)

### T-15 min: Open Tabs

| Tab | URL | Auth | Ready? |
|-----|-----|------|--------|
| 1 | Slide deck (Keynote/PDF) | N/A | [ ] |
| 2 | `console.gostoa.dev` | halliday | [ ] |
| 3 | `portal.gostoa.dev` | art3mis | [ ] |
| 4 | Terminal (iTerm2, 18pt) | TOKEN set | [ ] |
| 5 | `console.gostoa.dev/grafana` | admin | [ ] |

- [ ] All 5 tabs open and authenticated
- [ ] Tab order matches DEMO-NARRATIVE.md flow

### T-5 min: Final Verify

- [ ] Console dashboard loads with real data
- [ ] Portal API catalog loads
- [ ] Gateway health: `curl -s https://mcp.gostoa.dev/health` → 200
- [ ] Grafana shows live metrics

### T-0: Deep breath. You built this. You know every line.

---

## Plan B: Component Failure During Demo

| If This Breaks | Say This | Do This |
|----------------|----------|---------|
| **Console won't load** | "Let me show you the developer side" | Switch to Portal (Tab 3) |
| **Portal won't load** | "Let me go straight to the API" | Skip to Terminal (Tab 4), use cached token |
| **Gateway 500** | "Let me show you the recording" | Play backup video (5 min version) |
| **Auth fails** | _(say nothing)_ | Use cached token from `/tmp/demo-tokens.env` |
| **mTLS demo fails** | "Let me show you the JWT structure" | `echo $TOKEN_MTLS \| python3 -c "..."` to decode JWT, show `cnf` claim |
| **Grafana empty** | "Metrics are streaming in" | Show screenshot in slides, mention 29 dashboards |
| **MCP bridge fails** | "The bridge generates MCP tools from OpenAPI" | Show architecture slide, explain verbally |
| **Wifi down** | "Two seconds" | Switch to mobile hotspot, no apology |
| **Everything down** | "Let me show you the recording we did yesterday" | Play `demo-backup-2026-02-23.mp4`, no apology |

### Key Principle

**Never apologize for technical issues.** Instead:
- "Let me show you this another way"
- "Let me switch to the recording"
- "Let me show you the architecture instead"

The audience doesn't know your plan. Any pivot looks intentional if you stay calm.

---

## Plan C: Total Failure

If both live demo AND video backup fail:

1. **Stay calm.** Smile.
2. Open `DEMO-SLIDES.pdf` (offline, no internet needed)
3. Walk through slides with verbal descriptions: "Here's what you would see..."
4. Use the benchmark table (Slide 5) and GitOps comparison (Slide 6) as anchor points
5. Offer: "I'd like to schedule a 30-minute live session this week where I can show you everything running"
6. Share `docs.gostoa.dev` and `github.com/stoa-platform` for self-exploration

**This has never happened.** But if it does, the slides + your knowledge are enough. The demo is impressive, but the strategy is what sells.

---

## Post-Demo (within 1 hour)

- [ ] Collect contacts (LinkedIn, business cards, email)
- [ ] Note every question asked (exact wording if possible)
- [ ] Note any bugs or frictions encountered during demo
- [ ] Send follow-up email with:
  - `docs.gostoa.dev` link
  - `github.com/stoa-platform` link
  - Proposal for 2-hour technical workshop
- [ ] Update `DRY-RUN-1.md` with demo day report
- [ ] File Linear tickets for any bugs discovered
- [ ] Celebrate

---

*Generated for CAB-1075 — Demo Day Ready*
*Consolidates: DEMO-CHECKLIST.md + DEMO-PLAN-B.md + Linear ticket DoD*
*Last updated: 2026-02-15*
