#!/usr/bin/env bash
set -euo pipefail

LABEL="com.bedong.cursor-usage-notifier"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_DST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
SUPPORT_DIR="${HOME}/Library/Application Support/cursor-usage-notifier"
LOG_DIR="${HOME}/Library/Logs"
CONFIG_DST="${SUPPORT_DIR}/config.toml"
STDOUT_LOG="${LOG_DIR}/cursor-usage-notifier.log"
STDERR_LOG="${LOG_DIR}/cursor-usage-notifier.err.log"
NETSKOPE_CERT="/Library/Application Support/Netskope/STAgent/download/nscacert_combined.pem"

mkdir -p "${SUPPORT_DIR}" "${LOG_DIR}" "${HOME}/Library/LaunchAgents"

if [[ ! -f "${CONFIG_DST}" ]]; then
  cp "${PROJECT_DIR}/config.example.toml" "${CONFIG_DST}"
  echo "Created default config at ${CONFIG_DST}"
fi

python3 -m pip install --user -e "${PROJECT_DIR}" >/dev/null

PYTHON_BIN="$(python3 -m site --user-base)/bin/python3"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

SSL_CERT="${SSL_CERT_FILE:-}"
if [[ -z "${SSL_CERT}" && -f "${NETSKOPE_CERT}" ]]; then
  SSL_CERT="${NETSKOPE_CERT}"
fi

POLL_MINUTES=15
if [[ -f "${CONFIG_DST}" ]]; then
  POLL_MINUTES="$(python3 -c "import tomllib, pathlib; p=pathlib.Path('${CONFIG_DST}'); print(int(tomllib.loads(p.read_text()).get('poll_minutes', 15)))")"
fi
if [[ "${POLL_MINUTES}" -lt 1 ]]; then
  POLL_MINUTES=1
fi
START_INTERVAL=$((POLL_MINUTES * 60))

{
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
      <string>${PYTHON_BIN}</string>
      <string>-m</string>
      <string>cursor_usage_notifier</string>
      <string>check</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartInterval</key>
    <integer>${START_INTERVAL}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${STDOUT_LOG}</string>
    <key>StandardErrorPath</key>
    <string>${STDERR_LOG}</string>
EOF

  if [[ -n "${SSL_CERT}" ]]; then
    cat <<EOF
    <key>EnvironmentVariables</key>
    <dict>
      <key>SSL_CERT_FILE</key>
      <string>${SSL_CERT}</string>
    </dict>
EOF
  fi

  cat <<'EOF'
  </dict>
</plist>
EOF
} > "${PLIST_DST}"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_DST}"
launchctl enable "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true

echo "Installed launchd agent: ${LABEL}"
echo "Logs: ${STDOUT_LOG}"
