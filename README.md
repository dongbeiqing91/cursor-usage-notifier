# Cursor Usage Notifier

Lightweight macOS utility that polls Cursor dashboard usage and sends a Notification Center alert every time your current billing-cycle spend crosses another configurable USD threshold (default: **$50**).

## Requirements

- macOS
- Python 3.11+
- Signed-in Cursor IDE (local session token is read automatically)

## Quick start

```bash
cd /Users/bedong/Workspaces/cursor-usage-notifier
python3 -m pip install -e .
python3 -m cursor_usage_notifier check --dry-run
python3 -m cursor_usage_notifier check --notify-test
python3 -m cursor_usage_notifier check
```

## Configuration

Copy the example config:

```bash
mkdir -p ~/Library/Application\ Support/cursor-usage-notifier
cp config.example.toml ~/Library/Application\ Support/cursor-usage-notifier/config.toml
```

Settings:

| Key | Default | Description |
| --- | --- | --- |
| `threshold_usd` | `50` | Notify at each multiple of this amount |
| `poll_minutes` | `5` | Poll interval; used by `install-launchd.sh` as `StartInterval` |
| `sound` | `Glass` | macOS notification sound |

## Start / stop / login auto-start

Agent label: `com.bedong.cursor-usage-notifier`

### Start (install + load)

Installs the LaunchAgent, loads it, and runs a check immediately:

```bash
cd /Users/bedong/Workspaces/cursor-usage-notifier
chmod +x scripts/install-launchd.sh
./scripts/install-launchd.sh
```

Or start/restart an already-installed agent without reinstalling:

```bash
launchctl kickstart -k gui/$(id -u)/com.bedong.cursor-usage-notifier
```

### Stop (unload for this session)

Stops the agent until you load it again or log in again (if the plist remains installed):

```bash
launchctl bootout gui/$(id -u)/com.bedong.cursor-usage-notifier
```

### Enable login auto-start (开机启动)

`./scripts/install-launchd.sh` installs the plist to `~/Library/LaunchAgents/` with `RunAtLoad=true`, so the agent starts automatically when you log in to macOS.

If the plist is already present but unloaded, enable and load it:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bedong.cursor-usage-notifier.plist
launchctl enable gui/$(id -u)/com.bedong.cursor-usage-notifier
```

### Disable login auto-start (关闭开机启动)

Unload and remove the LaunchAgent plist so it will not start on the next login:

```bash
launchctl bootout gui/$(id -u)/com.bedong.cursor-usage-notifier 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.bedong.cursor-usage-notifier.plist
```

To re-enable later, run `./scripts/install-launchd.sh` again.

### Logs

- `~/Library/Logs/cursor-usage-notifier.log`
- `~/Library/Logs/cursor-usage-notifier.err.log`

Check status:

```bash
launchctl print gui/$(id -u)/com.bedong.cursor-usage-notifier
```

## Auth

Token resolution order:

1. `CURSOR_SESSION_TOKEN`
2. `WorkosCursorSessionToken`
3. Cursor local DB: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`

## Notes

- Uses unofficial Cursor dashboard endpoints; they may change.
- Spend source prefers on-demand cents from `/api/usage-summary`, with aggregated-event fallback.
- First run bootstraps existing milestones for the current cycle without sending backfilled alerts.
- `install-launchd.sh` forwards `SSL_CERT_FILE` (or Netskope cert if present) for corporate SSL inspection.
