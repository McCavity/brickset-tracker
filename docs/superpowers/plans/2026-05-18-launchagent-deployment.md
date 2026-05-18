# LaunchAgent Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the macOS LaunchAgent so brickset-tracker auto-starts at login, restarts on crash, and exposes a clean install/uninstall/status UX.

**Architecture:** In-repo plist template + a `launchagent.sh` bash script that templates the plist, picks a free port (probing upward from `PORT` in `.env`), writes the picked port back to `.env`, installs to `~/Library/LaunchAgents/`, loads via `launchctl`, and smoke-tests the HTTP endpoint. No Python code changes.

**Tech Stack:** macOS `launchctl` / `plist`, bash, `nc` (netcat) for port probing, `curl` for smoke checks, BSD `sed -i ''` for in-place edits.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/de.hhalfpap.brickset-tracker.plist.template` | The launchd contract (data). Three placeholders: `__PROJECT_ROOT__`, `__HOME__`, `__PORT__`. |
| `scripts/launchagent.sh` | Operator CLI: `install`, `uninstall`, `status`. Contains port discovery and `.env` rewrite. |
| `scripts/README.md` | Human-readable guide: how to run each command, where logs live, troubleshooting table. |
| `.env` | Gets a `PORT=8000` line appended (gitignored, per-machine value). |

## Task Order

Tasks are written so each one ends with a working, testable artifact:
1. **Task 1**: plist template (data file)
2. **Task 2**: `launchagent.sh` core (`install` happy path, no port discovery yet)
3. **Task 3**: port discovery + `.env` rewrite (the smart-port behaviour)
4. **Task 4**: `uninstall` + `status` subcommands
5. **Task 5**: `README.md`
6. **Task 6**: end-to-end manual smoke (install, kill-and-respawn, port-conflict, uninstall)
7. **Task 7**: update `task_plan.md` to mark Phase T complete

---

## Task 1: Create the plist template

**Files:**
- Create: `scripts/de.hhalfpap.brickset-tracker.plist.template`

- [ ] **Step 1: Write the template file verbatim**

Create `scripts/de.hhalfpap.brickset-tracker.plist.template` with this exact content:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>de.hhalfpap.brickset-tracker</string>

  <key>ProgramArguments</key>
  <array>
    <string>__PROJECT_ROOT__/.venv/bin/uvicorn</string>
    <string>main:app</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>__PORT__</string>
  </array>

  <key>WorkingDirectory</key>
  <string>__PROJECT_ROOT__</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>__PROJECT_ROOT__/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>__HOME__/Library/Logs/brickset-tracker.log</string>

  <key>StandardErrorPath</key>
  <string>__HOME__/Library/Logs/brickset-tracker.log</string>

  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>
```

- [ ] **Step 2: Verify the template parses as XML**

Run:

```bash
xmllint --noout scripts/de.hhalfpap.brickset-tracker.plist.template
```

Expected: exits 0, no output. (`xmllint` ships with macOS.)

Note: `plutil -lint` is the more authoritative check, but it rejects the unsubstituted placeholders (`__PROJECT_ROOT__` etc.) because they aren't valid in `<string>` typing for some keys. We'll run `plutil -lint` on the **rendered** plist inside `launchagent.sh` (Task 2 Step 4).

- [ ] **Step 3: Commit**

```bash
git add scripts/de.hhalfpap.brickset-tracker.plist.template
git commit -m "feat(launchd): plist template for brickset-tracker LaunchAgent"
```

---

## Task 2: `launchagent.sh` — core `install` (no port discovery yet)

This task lands the script with a simple "read `PORT` from `.env` or default 8000" — no scanning, no rewriting. Port discovery layers in Task 3.

**Files:**
- Create: `scripts/launchagent.sh`
- Modify: `.env` (append one line)

- [ ] **Step 1: Append `PORT=8000` to `.env`**

Run:

```bash
printf '\nPORT=8000\n' >> .env
```

Verify:

```bash
grep '^PORT=' .env
```

Expected: `PORT=8000`

- [ ] **Step 2: Create `scripts/launchagent.sh` with the install command**

Create `scripts/launchagent.sh`:

```bash
#!/usr/bin/env bash
# Manage the brickset-tracker LaunchAgent.
# Usage: ./scripts/launchagent.sh {install|uninstall|status}
set -euo pipefail

LABEL="de.hhalfpap.brickset-tracker"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="${PROJECT_ROOT}/scripts/${LABEL}.plist.template"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG="${HOME}/Library/Logs/brickset-tracker.log"

read_port_from_env() {
  local p
  p="$(grep -E '^PORT=' "${PROJECT_ROOT}/.env" 2>/dev/null | cut -d= -f2 | tr -d ' "' || true)"
  echo "${p:-8000}"
}

cmd_install() {
  # Pre-flight: venv must exist
  if [[ ! -x "${PROJECT_ROOT}/.venv/bin/uvicorn" ]]; then
    echo "ERROR: ${PROJECT_ROOT}/.venv/bin/uvicorn not found."
    echo "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
  fi

  # If already loaded, unload first so the new plist takes effect
  if launchctl list "${LABEL}" >/dev/null 2>&1; then
    launchctl unload "${PLIST}" 2>/dev/null || true
  fi

  local port
  port="$(read_port_from_env)"

  # Render template
  sed -e "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
      -e "s|__HOME__|${HOME}|g" \
      -e "s|__PORT__|${port}|g" \
      "${TEMPLATE}" > "${PLIST}"

  # Validate the rendered plist
  if ! plutil -lint "${PLIST}" >/dev/null; then
    echo "ERROR: rendered plist failed plutil -lint. Aborting."
    rm -f "${PLIST}"
    exit 1
  fi

  # Ensure log directory exists (LaunchAgents won't create parent dirs)
  mkdir -p "$(dirname "${LOG}")"

  # Load
  launchctl load -w "${PLIST}"

  # Smoke check: poll for up to 5s (one probe per second)
  local i
  for i in 1 2 3 4 5; do
    if curl -fsS "http://localhost:${port}/" >/dev/null 2>&1; then
      echo "✓ LaunchAgent installed and responding on http://localhost:${port}/"
      echo "  Logs:  ${LOG}"
      echo "  Plist: ${PLIST}"
      return 0
    fi
    sleep 1
  done
  echo "ERROR: LaunchAgent loaded but server did not respond on port ${port} within 5s."
  echo "Check logs: tail -50 ${LOG}"
  exit 1
}

case "${1:-}" in
  install) cmd_install ;;
  *) echo "Usage: $0 {install|uninstall|status}"; exit 2 ;;
esac
```

- [ ] **Step 3: Make the script executable**

Run:

```bash
chmod +x scripts/launchagent.sh
```

- [ ] **Step 4: Manually verify the install command works**

Run:

```bash
./scripts/launchagent.sh install
```

Expected output (port may differ if 8000 is already busy in some unrelated way — that's still OK at this stage, since Task 3 adds the actual discovery; here we're just testing the happy path):

```
✓ LaunchAgent installed and responding on http://localhost:8000/
  Logs:  /Users/hhalfpap/Library/Logs/brickset-tracker.log
  Plist: /Users/hhalfpap/Library/LaunchAgents/de.hhalfpap.brickset-tracker.plist
```

If this fails because port 8000 is busy, run `lsof -nP -iTCP:8000 -sTCP:LISTEN` to see what's holding it. Stop that process, then re-run `install`. (Port discovery in Task 3 will make this automatic.)

Confirm the plist is loaded:

```bash
launchctl list de.hhalfpap.brickset-tracker
```

Expected: a block with `"PID" = <some-int>;` and `"LastExitStatus" = 0;`.

Confirm the server actually responds:

```bash
curl -s http://localhost:8000/ | head -1
```

Expected: HTML starting with `<!DOCTYPE html>` (the index page).

- [ ] **Step 5: Commit**

```bash
git add scripts/launchagent.sh .env
```

WAIT — `.env` is gitignored. The `git add` will silently skip it. Verify:

```bash
git status --short
```

Expected: only `scripts/launchagent.sh` should be staged (and possibly `scripts/launchagent.sh` as a new file). `.env` must NOT appear in the diff.

If `.env` somehow appears, remove it from staging:

```bash
git restore --staged .env
```

Then commit:

```bash
git commit -m "feat(launchd): launchagent.sh with install command (no port discovery yet)"
```

---

## Task 3: Port discovery + `.env` rewrite

Add the smart-port behaviour: scan upward from the value in `.env`, pick the first free port in a 100-port window, write the chosen port back to `.env`.

**Files:**
- Modify: `scripts/launchagent.sh`

- [ ] **Step 1: Add `find_free_port` and `write_port_to_env` helpers**

Open `scripts/launchagent.sh`. After the `read_port_from_env()` function, add two new helper functions. The block to insert (placed right after `read_port_from_env()`):

```bash
find_free_port() {
  # Scan from $1 upward for up to 100 ports; echo first free, return 1 if none.
  local start="$1"
  local max=$((start + 99))
  local p
  for ((p=start; p<=max; p++)); do
    if ! nc -z -G 1 127.0.0.1 "${p}" >/dev/null 2>&1; then
      echo "${p}"
      return 0
    fi
  done
  return 1
}

write_port_to_env() {
  local port="$1"
  local env="${PROJECT_ROOT}/.env"
  if grep -qE '^PORT=' "${env}" 2>/dev/null; then
    # BSD sed: -i needs '' for in-place with no backup
    sed -i '' -E "s|^PORT=.*|PORT=${port}|" "${env}"
  else
    printf '\nPORT=%s\n' "${port}" >> "${env}"
  fi
}
```

- [ ] **Step 2: Wire discovery into `cmd_install`**

In `cmd_install`, replace the single line:

```bash
  local port
  port="$(read_port_from_env)"
```

with:

```bash
  local start_port
  start_port="$(read_port_from_env)"

  local port
  if ! port="$(find_free_port "${start_port}")"; then
    echo "ERROR: no free port in ${start_port}..$((start_port + 99))."
    echo "Check what's bound: lsof -nP -iTCP -sTCP:LISTEN | grep 80"
    exit 1
  fi

  if [[ "${port}" != "${start_port}" ]]; then
    echo "Port ${start_port} busy — using ${port} instead."
  fi
  write_port_to_env "${port}"
```

- [ ] **Step 3: Verify the happy path still works**

Run:

```bash
./scripts/launchagent.sh install
```

Expected: same success message as Task 2 Step 4. `.env` should still read `PORT=8000` (no change because 8000 was already what was requested AND was free at the moment of probe — `nc -z` against a port the server itself just freed during unload is non-zero / not listening).

Wait — there's a subtle ordering issue here. The script:
1. Unloads any existing instance (frees the port if we were the listener)
2. Probes for free port
3. Loads the new plist

So a re-install where we previously held the port WILL see the port as free during step 2 (because step 1 freed it). That's correct. If a DIFFERENT process is holding the port, probe will see it as busy and we walk upward.

Manually verify `.env` is unchanged after a same-port re-install:

```bash
grep '^PORT=' .env
```

Expected: `PORT=8000`

- [ ] **Step 4: Verify the conflict path works**

In one terminal, start a blocker that holds port 8000:

```bash
nc -l 8000 &
NC_PID=$!
sleep 1   # let nc actually bind
```

In the same terminal (or another), run install:

```bash
./scripts/launchagent.sh install
```

Expected: a line `Port 8000 busy — using 8001 instead.` somewhere in the output, followed by the success message with `http://localhost:8001/`.

Verify `.env` was updated:

```bash
grep '^PORT=' .env
```

Expected: `PORT=8001`

Verify the server is responding on 8001:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/
```

Expected: `200`

Clean up the blocker and re-install to settle the system on 8000:

```bash
kill "${NC_PID}" 2>/dev/null || true
# Manually reset .env so the next install tries 8000 again
sed -i '' -E 's|^PORT=.*|PORT=8000|' .env
./scripts/launchagent.sh install
```

Expected: success message with `http://localhost:8000/`.

- [ ] **Step 5: Commit**

```bash
git add scripts/launchagent.sh
git commit -m "feat(launchd): auto-pick free port at install (scans PORT..PORT+99, rewrites .env)"
```

---

## Task 4: `uninstall` and `status` subcommands

**Files:**
- Modify: `scripts/launchagent.sh`

- [ ] **Step 1: Add the two new commands**

In `scripts/launchagent.sh`, after `cmd_install()`, add:

```bash
cmd_uninstall() {
  if launchctl list "${LABEL}" >/dev/null 2>&1; then
    launchctl unload "${PLIST}" 2>/dev/null || true
  fi
  rm -f "${PLIST}"
  echo "✓ LaunchAgent uninstalled. (Log file preserved at ${LOG}.)"
}

cmd_status() {
  if ! launchctl list "${LABEL}" >/dev/null 2>&1; then
    echo "LaunchAgent not loaded. Install with: $0 install"
    exit 1
  fi
  launchctl list "${LABEL}"
  echo ""
  local port
  port="$(read_port_from_env)"
  if curl -fsS -o /dev/null -w "HTTP %{http_code} on http://localhost:${port}/\n" "http://localhost:${port}/"; then
    echo "✓ Server is responding"
  else
    echo "✗ Server is NOT responding"
    exit 1
  fi
}
```

- [ ] **Step 2: Wire the new commands into the case dispatcher**

Replace the existing `case` block at the bottom of the script:

```bash
case "${1:-}" in
  install) cmd_install ;;
  *) echo "Usage: $0 {install|uninstall|status}"; exit 2 ;;
esac
```

with:

```bash
case "${1:-}" in
  install)   cmd_install ;;
  uninstall) cmd_uninstall ;;
  status)    cmd_status ;;
  *) echo "Usage: $0 {install|uninstall|status}"; exit 2 ;;
esac
```

- [ ] **Step 3: Verify `status` works (server should still be loaded from Task 3)**

```bash
./scripts/launchagent.sh status
```

Expected:

```
"de.hhalfpap.brickset-tracker" = {
    ...
    "PID" = <some-int>;
    "LastExitStatus" = 0;
    ...
};

HTTP 200 on http://localhost:8000/
✓ Server is responding
```

- [ ] **Step 4: Verify `uninstall` works**

```bash
./scripts/launchagent.sh uninstall
```

Expected:

```
✓ LaunchAgent uninstalled. (Log file preserved at /Users/hhalfpap/Library/Logs/brickset-tracker.log.)
```

Confirm the plist is gone and `launchctl` doesn't know about it:

```bash
ls ~/Library/LaunchAgents/de.hhalfpap.brickset-tracker.plist 2>&1
launchctl list de.hhalfpap.brickset-tracker 2>&1
```

Expected:
- First: `No such file or directory`
- Second: `Could not find service "de.hhalfpap.brickset-tracker" in domain ...` (or similar non-zero exit)

Verify `status` reports the missing-agent case:

```bash
./scripts/launchagent.sh status
```

Expected:

```
LaunchAgent not loaded. Install with: ./scripts/launchagent.sh install
```

Exit code should be 1:

```bash
./scripts/launchagent.sh status; echo "exit=$?"
```

Expected: `exit=1`

- [ ] **Step 5: Re-install so the system is back in the running state**

```bash
./scripts/launchagent.sh install
```

Expected: success with `http://localhost:8000/`.

- [ ] **Step 6: Commit**

```bash
git add scripts/launchagent.sh
git commit -m "feat(launchd): add uninstall and status subcommands"
```

---

## Task 5: Operator README

**Files:**
- Create: `scripts/README.md`

- [ ] **Step 1: Write the README**

Create `scripts/README.md`:

```markdown
# LaunchAgent operator guide

A macOS launchd job that runs the Brickset Tracker server in the background:
auto-starts at login, auto-restarts on crash, logs to
`~/Library/Logs/brickset-tracker.log`.

## Install

```bash
./scripts/launchagent.sh install
```

The script reads `PORT` from `.env` (default 8000). If that port is already
busy, it scans upward (up to PORT+99) and uses the first free one,
rewriting `.env` with the new value. The chosen port is printed at the end
of the install output. The server is then reachable at `http://localhost:$PORT/`
and will come back automatically after reboot.

## Status / uninstall

```bash
./scripts/launchagent.sh status      # is it loaded? is it responding?
./scripts/launchagent.sh uninstall   # unload and remove the plist (log preserved)
```

## Logs

```bash
tail -f ~/Library/Logs/brickset-tracker.log
```

If the install smoke-test fails, that file is where uvicorn's traceback lives.

## When to re-run install

- After editing `PORT` in `.env`
- After moving the project directory (the plist hard-codes the absolute path)
- After deleting/recreating the `.venv/`

Updating uvicorn inside the existing `.venv/` does NOT require a re-install;
the plist points at the venv's `uvicorn` symlink and KeepAlive picks up the
new binary on the next restart. To force the restart without waiting for a
crash:

```bash
launchctl kickstart -k gui/$UID/de.hhalfpap.brickset-tracker
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ERROR: ... .venv/bin/uvicorn not found` | The Python venv is missing. Run `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`. |
| `Port N busy — using N+1 instead.` | Something else was listening on the original port. `.env` has been updated; everything still works, just on a different port. |
| `ERROR: LaunchAgent loaded but server did not respond ... within 5s` | A startup exception, port grabbed between probe and load, or a slow first-request. Check `~/Library/Logs/brickset-tracker.log`. |
| Server stops working after a `git pull` | Re-run `./scripts/launchagent.sh install` to reload with the latest code. |
| `LaunchAgent not loaded.` from `status` | The agent is not installed (or was uninstalled). Run `install`. |
| `ERROR: no free port in 8000..8099` | Something is very wrong — over 100 listeners in that range. Use `lsof -nP -iTCP -sTCP:LISTEN | grep 80` to investigate. |
```

- [ ] **Step 2: Verify the README renders cleanly**

```bash
grep -c '^|' scripts/README.md
```

Expected: 7 (one header row + 6 troubleshooting entries).

- [ ] **Step 3: Commit**

```bash
git add scripts/README.md
git commit -m "docs(launchd): operator guide for the LaunchAgent script"
```

---

## Task 6: End-to-end manual smoke

This task has no code changes. It is the contract verification per the spec's "Done When" section. The goal is to prove the LaunchAgent actually behaves the way it claims.

**Files:** None modified. (Pure verification.)

- [ ] **Step 1: Confirm running state**

```bash
./scripts/launchagent.sh status
```

Expected: PID + HTTP 200 on the configured port. Note the PID for the next step.

- [ ] **Step 2: Kill the uvicorn process; confirm launchd respawns it**

```bash
launchctl list de.hhalfpap.brickset-tracker | grep PID
# Note the PID, then:
kill -9 <PID>
sleep 2
./scripts/launchagent.sh status
```

Expected: a DIFFERENT PID (proving launchd respawned a new process), still HTTP 200.

- [ ] **Step 3: Port conflict happy path**

This is the same scenario as Task 3 Step 4. Re-run it now as part of the full E2E:

```bash
# Uninstall first so the port frees up cleanly
./scripts/launchagent.sh uninstall

# Block port 8000
nc -l 8000 &
NC_PID=$!
sleep 1

# Reset .env to 8000 so we re-test discovery
sed -i '' -E 's|^PORT=.*|PORT=8000|' .env

# Install — should pick 8001 and write that to .env
./scripts/launchagent.sh install

# Verify
grep '^PORT=' .env
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/
```

Expected: `PORT=8001`, HTTP 200.

Clean up:

```bash
kill "${NC_PID}" 2>/dev/null || true
./scripts/launchagent.sh uninstall
sed -i '' -E 's|^PORT=.*|PORT=8000|' .env
./scripts/launchagent.sh install
```

- [ ] **Step 4: Reboot test (optional but recommended)**

This is the actual contract the LaunchAgent guarantees. The user runs this manually:

1. Log out from macOS.
2. Log back in.
3. From a terminal: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:$(grep '^PORT=' .env | cut -d= -f2)/`

Expected: `200`, with no manual `install` having been run between log-out and log-in.

If the user prefers not to log out, the next planned reboot/login cycle will demonstrate the same thing. This step is documented but not required to mark Task 6 complete — the LaunchAgent's `RunAtLoad: true` behaviour is well-defined and the script already verified that loading works.

- [ ] **Step 5: Run the full pytest suite — no regression**

```bash
.venv/bin/python -m pytest -q
```

Expected: `153 passed`.

(No tests were added or modified in this phase; this just confirms the `.env` change doesn't break the existing suite.)

- [ ] **Step 6: No commit needed for this task**

This task is verification, not code. Skip the commit step.

---

## Task 7: Update task plan — V1 complete

**Files:**
- Modify: `~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md`

- [ ] **Step 1: Find the Phase T line**

Read the file and locate the `- [ ] **T — Trigger**:` checklist entry (around line 18 of the original).

- [ ] **Step 2: Mark Phase T complete**

In `~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md`, change:

```
- [ ] **T — Trigger**: Deferred — agreed approach is a macOS LaunchAgent at `~/Library/LaunchAgents/de.hhalfpap.brickset-tracker.plist` (auto-start at login, auto-restart on crash, logs to `~/Library/Logs/brickset-tracker.log`). Will be the final task once all loose ends are tied up.
```

to:

```
- [x] **T — Trigger**: ✅ COMPLETE 2026-05-18 — macOS LaunchAgent at `~/Library/LaunchAgents/de.hhalfpap.brickset-tracker.plist`. Install via `./scripts/launchagent.sh install` (auto-picks free port from PORT in .env). Auto-start at login, auto-restart on crash, logs to `~/Library/Logs/brickset-tracker.log`.
```

- [ ] **Step 3: Mark V1 done in the Road to V1 list**

In the same file, change the last numbered entry from:

```
9. **Phase T** — LaunchAgent deployment (see above)
10. **V1 done** — usable small local server
```

to:

```
9. ~~**Phase T** — LaunchAgent deployment~~ **✅ COMPLETE 2026-05-18** (153 tests, +7 commits across scripts/ + .env)
10. **V1 done** ✅ 2026-05-18 — usable small local server, running as a LaunchAgent
```

- [ ] **Step 4: Verify there's only one B.L.A.S.T. entry to update**

```bash
grep -c "T — Trigger" ~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md
```

Expected: `1` (the line modified in Step 2). The B.L.A.S.T. checklist and the detailed entry are the same line. If the grep returns more than 1, repeat Step 2's edit on each remaining occurrence.

- [ ] **Step 5: No git commit**

`task_plan.md` lives in `~/.claude/projects/.../memory/` — outside the repo. No commit needed.

---

## Final Verification

- [ ] **Step 1: Git log shows the expected commits**

```bash
git log --oneline 9ed9b5e..HEAD
```

Expected (5 commits since the spec):
- `<sha> docs(launchd): operator guide for the LaunchAgent script`
- `<sha> feat(launchd): add uninstall and status subcommands`
- `<sha> feat(launchd): auto-pick free port at install (scans PORT..PORT+99, rewrites .env)`
- `<sha> feat(launchd): launchagent.sh with install command (no port discovery yet)`
- `<sha> feat(launchd): plist template for brickset-tracker LaunchAgent`

- [ ] **Step 2: Repo shows three new files in `scripts/`**

```bash
ls scripts/
```

Expected:
```
README.md
de.hhalfpap.brickset-tracker.plist.template
launchagent.sh
```

- [ ] **Step 3: Final pytest run**

```bash
.venv/bin/python -m pytest -q
```

Expected: `153 passed`.

- [ ] **Step 4: Server is running**

```bash
./scripts/launchagent.sh status
```

Expected: HTTP 200 on the configured port.

V1 is done.
