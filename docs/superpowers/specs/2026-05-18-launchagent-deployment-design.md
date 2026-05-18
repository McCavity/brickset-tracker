# LaunchAgent Deployment — Design

**Status:** Approved 2026-05-18
**Project:** brickset-tracker
**Phase:** T — Trigger (the final V1 work)

## Goal

Run the Brickset Tracker server as a macOS LaunchAgent so it starts automatically at login, restarts after a crash, and logs to a predictable location. The deliverable is an in-repo template plus an operator script (`install` / `uninstall` / `status`) that handles plist rendering, port-conflict resolution, and a startup smoke test.

After this iteration ships, V1 is done.

## Out of Scope

- LaunchDaemon (system-wide) install — this is a personal, single-user app.
- LAN exposure — server binds to `127.0.0.1` only.
- Log rotation — `~/Library/Logs/brickset-tracker.log` grows unbounded for V1. Revisit if it becomes a real problem.
- Cross-machine portability beyond the install script's templating (e.g. no Homebrew formula, no Docker image).
- Tests in `pytest` — the deliverable is shell + plist, smoke-tested by hand.

## Files Added

```
scripts/
├── de.hhalfpap.brickset-tracker.plist.template   # plist with __PROJECT_ROOT__ / __HOME__ / __PORT__ placeholders
├── launchagent.sh                                 # ./launchagent.sh install | uninstall | status
└── README.md                                       # operator guide + troubleshooting table
```

Plus one small change:
- `.env` gets a new `PORT=8000` line. `.env` is gitignored, so this is a per-machine value.

No changes to any Python source. `main.py`'s docstring still says `uvicorn main:app --reload --port 8000` for development; production invocation lives in the plist.

## Plist Template

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

### Choices encoded in the plist

- **`--host 127.0.0.1`** — loopback only. No LAN exposure for a personal tool.
- **`KeepAlive: true`** — launchd restarts the process on any non-zero exit. Matches the original Phase-T spec ("auto-restart on crash").
- **`StandardOutPath` == `StandardErrorPath`** — uvicorn's startup banner and any traceback land in the same file, in order. macOS creates the file on first write.
- **`ProcessType: Background`** — applies background-app QoS (lower priority on battery, no AppNap surprises).
- **No `--reload`** — production mode, no file watcher.
- **Three placeholders** (`__PROJECT_ROOT__`, `__HOME__`, `__PORT__`) substituted by `sed` at install time.

## Operator Script (`scripts/launchagent.sh`)

Three subcommands, no dependencies beyond `launchctl`, `curl`, `nc`, `sed`, `grep`. ~80 lines of bash.

### `install` flow

1. **Pre-flight:** `.venv/bin/uvicorn` must exist; otherwise abort with a clear instruction to create the venv.
2. **Unload-if-loaded:** `launchctl unload` the existing plist (idempotent — re-running `install` cleanly replaces).
3. **Find a free port:** read `PORT` from `.env` (default 8000), probe with `nc -z -G 1 127.0.0.1 <port>`. If busy, scan upward to `start+99`. If none free in that window, abort with "Check what's bound: `lsof -nP -iTCP -sTCP:LISTEN | grep 80`".
4. **Persist the picked port:** rewrite the `PORT=` line in `.env` (or append it if missing) so `status`/`uninstall` use the same value.
5. **Render the plist:** `sed` substitutes the three placeholders, writes to `~/Library/LaunchAgents/de.hhalfpap.brickset-tracker.plist`.
6. **`mkdir -p ~/Library/Logs`** — exists on every Mac, but cheap to ensure.
7. **`launchctl load -w`** the plist.
8. **Smoke check:** poll `curl -fsS http://localhost:$PORT/` for up to 5 seconds (one probe per second). On success: print the URL, log path, and plist path. On timeout: print "loaded but did not respond — check logs: `tail -50 ~/Library/Logs/brickset-tracker.log`" and exit 1.

### `uninstall` flow

`launchctl unload` (tolerate "not loaded"), `rm -f` the plist, print confirmation. Log file is preserved.

### `status` flow

Print `launchctl list de.hhalfpap.brickset-tracker` (exits 1 if not loaded). Then `curl` the URL and report whether the server is responding.

### Port discovery details

```bash
find_free_port() {
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
```

- `nc -z` (zero-IO mode): exits 0 if a listener is present, non-zero if connection refused. Reliable on loopback.
- `-G 1`: 1-second connect timeout per probe so a stuck socket can't hang the install.
- Window cap of 100 ports — if 8000–8099 are all bound, something is wrong and the operator should investigate rather than letting the script walk to 60000.

### `.env` rewrite logic

```bash
write_port_to_env() {
  local port="$1"
  local env="${PROJECT_ROOT}/.env"
  if grep -qE '^PORT=' "${env}" 2>/dev/null; then
    sed -i '' -E "s|^PORT=.*|PORT=${port}|" "${env}"   # BSD sed needs '' arg
  else
    printf '\nPORT=%s\n' "${port}" >> "${env}"
  fi
}
```

BSD `sed -i ''` (with the empty backup-suffix argument) is the macOS-correct form. The function is invoked only by `install`, never by `uninstall` or `status`.

### Race window (acknowledged, not mitigated)

Between the port probe and `launchctl load`, another process could grab the chosen port. On a single-user Mac this is vanishingly unlikely; if it does happen, uvicorn will fail to bind, KeepAlive will respawn it tightly, the smoke check will time out, and the install script will exit 1 with the existing "check logs" message. Acceptable for V1.

## `scripts/README.md`

Short operator doc. Sections:
- **Install / Status / Uninstall** — one-line commands each.
- **Logs** — `tail -f ~/Library/Logs/brickset-tracker.log`.
- **When to re-run install** — after editing `PORT` in `.env`, moving the project directory, or recreating `.venv/`. (Updating uvicorn inside the existing `.venv/` does NOT require a re-install; the plist points at the venv's `uvicorn` symlink, and `KeepAlive: true` means the next crash-and-restart picks up the new binary. A `launchctl kickstart -k gui/$UID/de.hhalfpap.brickset-tracker` forces it.)
- **Troubleshooting** — table covering: missing venv, port conflict, post-`git-pull` staleness, "loaded but not responding."

## Testing Strategy

No `pytest` additions — this is shell + plist, not application logic. Manual smoke tests on this Mac:

1. `./scripts/launchagent.sh install` → expect success message and `curl http://localhost:$PORT/` returns 200.
2. `./scripts/launchagent.sh status` → "Server is responding."
3. `kill -9 <uvicorn pid>` → launchd respawns within ~1s; `status` still green.
4. `./scripts/launchagent.sh uninstall` → `launchctl list de.hhalfpap.brickset-tracker` fails.
5. Re-`install` to leave the system in the running state.
6. **Reboot test** (manual, optional): log out and back in; verify `curl http://localhost:$PORT/` returns 200 without any manual action. This is the actual contract the LaunchAgent guarantees.

A second port-conflict test:
7. Start a separate `nc -l 8000` in another terminal. Run `./scripts/launchagent.sh install`. Expect "Port 8000 busy — using 8001 instead." `.env` should now read `PORT=8001`.

`pytest -q` before and after must show 153 passing — no regression in app behaviour.

## Risk + Migration

- **No app source changes.** Production code is untouched.
- **Single-machine deployment** — the plist hard-codes `/Users/hhalfpap/git/projects/own/brickset-tracker`. Moving the project requires re-running `install`.
- **No state migration.** SQLite DB and `uploads/` already live in the project tree; the LaunchAgent just runs the same uvicorn in the same `WorkingDirectory`.
- **`.env` mutation** — the install script edits `.env` (replacing or appending the `PORT` line). `.env` is gitignored, so this never affects the repo.

## Done When

- `./scripts/launchagent.sh install` succeeds and the server responds on the chosen port.
- Reboot → log back in → server is automatically up. (Manual verification step.)
- `pytest -q` still passes 153/153.
- `~/.claude/projects/<project>/memory/task_plan.md` updated: Phase T ✅, V1 declared done.
