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
| `ERROR: LaunchAgent loaded but server did not respond ... within 15s` | A startup exception, port grabbed between probe and load, or a slow first-request. Check `~/Library/Logs/brickset-tracker.log`. |
| Server stops working after a `git pull` | Re-run `./scripts/launchagent.sh install` to reload with the latest code. |
| `LaunchAgent not loaded.` from `status` | The agent is not installed (or was uninstalled). Run `install`. |
| `ERROR: no free port in 8000..8099` | Something is very wrong — over 100 listeners in that range. Use `lsof -nP -iTCP -sTCP:LISTEN | grep 80` to investigate. |
