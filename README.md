# Cursor Usage Notifier

Lightweight macOS utility that polls Cursor dashboard usage and sends a **sticky** top-right alert every time your current billing-cycle spend crosses another configurable USD threshold (default: **$50**). Alerts stay on screen until you click **Close**.

Each successful poll is also stored in a local SQLite history DB and served by a localhost dashboard with monthly trend charts.

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
python3 -m cursor_usage_notifier notify-now
python3 -m cursor_usage_notifier check
python3 -m cursor_usage_notifier serve
```

Open the dashboard at [http://127.0.0.1:8765](http://127.0.0.1:8765).

### Manual usage notification

Fetch current spend and pop one macOS notification immediately (does not change milestone state):

```bash
python3 -m cursor_usage_notifier notify-now
```

### Usage history dashboard

```bash
python3 -m cursor_usage_notifier serve
# or override bind address
python3 -m cursor_usage_notifier serve --host 127.0.0.1 --port 8765
```

Open without remembering the URL/port:

```bash
python3 -m cursor_usage_notifier open-dashboard
```

Or in Alfred type **`cursor-dash`** and press Enter.

The page shows:

- Month picker
- Cumulative spend trend
- Daily spend bars
- Daily detail table (day spend / cumulative / % of quota)

History file: `~/Library/Application Support/cursor-usage-notifier/history.sqlite`

### Alfred workflow

- **`cursor-usage`**: sticky notification with current spend
- **`cursor-dash`**: open the local dashboard in your browser

Repo copy: [`alfred/Cursor Usage.alfredworkflow`](alfred/Cursor%20Usage.alfredworkflow) (double-click to reinstall)

If Alfred does not show it yet, open Alfred Preferences → Workflows and confirm **Cursor Usage Notifier** is enabled.

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
| `web_host` | `127.0.0.1` | Dashboard bind host |
| `web_port` | `8765` | Dashboard bind port |
| `history_path` | `~/Library/Application Support/cursor-usage-notifier/history.sqlite` | Snapshot DB |

## Start / stop / login auto-start

Agent labels:

- `com.bedong.cursor-usage-notifier` — poller
- `com.bedong.cursor-usage-web` — dashboard (`KeepAlive`)

### Start (install + load)

Installs both LaunchAgents, loads them, and runs a check immediately:

```bash
cd /Users/bedong/Workspaces/cursor-usage-notifier
chmod +x scripts/install-launchd.sh
./scripts/install-launchd.sh
```

Or start/restart an already-installed agent without reinstalling:

```bash
launchctl kickstart -k gui/$(id -u)/com.bedong.cursor-usage-notifier
launchctl kickstart -k gui/$(id -u)/com.bedong.cursor-usage-web
```

### Stop (unload for this session)

```bash
launchctl bootout gui/$(id -u)/com.bedong.cursor-usage-notifier
launchctl bootout gui/$(id -u)/com.bedong.cursor-usage-web
```

### Enable login auto-start (开机启动)

`./scripts/install-launchd.sh` installs both plists under `~/Library/LaunchAgents/` with `RunAtLoad=true` (web agent also uses `KeepAlive`).

### Disable login auto-start (关闭开机启动)

```bash
launchctl bootout gui/$(id -u)/com.bedong.cursor-usage-notifier 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.bedong.cursor-usage-web 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.bedong.cursor-usage-notifier.plist
rm -f ~/Library/LaunchAgents/com.bedong.cursor-usage-web.plist
```

To re-enable later, run `./scripts/install-launchd.sh` again.

### Logs

- `~/Library/Logs/cursor-usage-notifier.log`
- `~/Library/Logs/cursor-usage-notifier.err.log`
- `~/Library/Logs/cursor-usage-web.log`
- `~/Library/Logs/cursor-usage-web.err.log`

Check status:

```bash
launchctl print gui/$(id -u)/com.bedong.cursor-usage-notifier
launchctl print gui/$(id -u)/com.bedong.cursor-usage-web
```

## Auth

Token resolution order:

1. `CURSOR_SESSION_TOKEN`
2. `WorkosCursorSessionToken`
3. Cursor local DB: `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`

## Notes

- Uses unofficial Cursor dashboard endpoints; they may change.
- Spend source prefers personal `individualUsage.overall.used` (not team on-demand).
- Notifications use bundled [`bin/alerter`](bin/alerter) with `--timeout 0` so they stay until you click **Close**.
- First run bootstraps existing milestones for the current cycle without sending backfilled alerts.
- Charts only include months/days after snapshots start being recorded (no API backfill).
- `install-launchd.sh` forwards `SSL_CERT_FILE` (or Netskope cert if present) for corporate SSL inspection.
- Dashboard binds to localhost only by default.
