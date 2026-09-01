#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${project_dir}"

command -v uv >/dev/null
command -v npm >/dev/null
command -v curl >/dev/null
command -v unzip >/dev/null

verification_root=$(mktemp -d "${TMPDIR:-/tmp}/community-intelligence-release.XXXXXX")
server_pid=""

cleanup() {
  if [[ -n "${server_pid}" ]]; then
    kill "${server_pid}" 2>/dev/null || true
    wait "${server_pid}" 2>/dev/null || true
  fi
  if [[ -d "${verification_root}" && "${verification_root}" == *community-intelligence-release.* ]]; then
    rm -rf -- "${verification_root}"
  fi
}
trap cleanup EXIT

uv sync --locked
uv run ruff check src tests
uv run pytest -q

npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium

uv build --out-dir "${verification_root}/dist"
wheel_path=$(find "${verification_root}/dist" -maxdepth 1 -name '*.whl' -print -quit)
if [[ -z "${wheel_path}" ]]; then
  echo "Release verification failed: wheel not produced." >&2
  exit 1
fi

wheel_listing="${verification_root}/wheel-files.txt"
unzip -Z1 "${wheel_path}" > "${wheel_listing}"
grep -qx 'community_intelligence/web/static/index.html' "${wheel_listing}"
grep -Eq '^community_intelligence/web/static/assets/.*\.js$' "${wheel_listing}"
grep -Eq '^community_intelligence/web/static/assets/.*\.css$' "${wheel_listing}"

uv venv "${verification_root}/wheel-venv" --python 3.11
wheel_python="${verification_root}/wheel-venv/bin/python"
wheel_command="${verification_root}/wheel-venv/bin/community-intelligence"
uv pip install --python "${wheel_python}" "${wheel_path}"
"${wheel_command}" --help >/dev/null
"${wheel_command}" demo --workspace "${verification_root}/demo" --messages 120 >/dev/null
"${wheel_command}" import telegram \
  --input frontend/e2e/fixtures/telegram-export.json \
  --output "${verification_root}/telegram-dataset" \
  --language en >/dev/null
"${wheel_command}" analyze \
  --input "${verification_root}/telegram-dataset" \
  --output "${verification_root}/telegram-report" >/dev/null

verify_port=${COMMUNITY_INTELLIGENCE_VERIFY_PORT:-8876}
COMMUNITY_INTELLIGENCE_DATA_DIR="${verification_root}/service-data" \
  "${wheel_command}" serve --no-open --port "${verify_port}" \
  >"${verification_root}/server.log" 2>&1 &
server_pid=$!

for attempt in $(seq 1 50); do
  if curl --fail --silent "http://127.0.0.1:${verify_port}/api/health" >/dev/null; then
    break
  fi
  sleep 0.2
done

health_json=$(curl --fail --silent "http://127.0.0.1:${verify_port}/api/health")
homepage_html=$(curl --fail --silent "http://127.0.0.1:${verify_port}/")
[[ "${health_json}" == *'"status":"ok"'* ]]
[[ "${homepage_html}" == *'Community Intelligence'* ]]
COMMUNITY_INTELLIGENCE_BASE_URL="http://127.0.0.1:${verify_port}" \
  npm --prefix frontend run test:e2e

echo "Release verification passed: tests, frontend build, wheel contents, clean install, demo, Telegram import, local service, and browser flows."
