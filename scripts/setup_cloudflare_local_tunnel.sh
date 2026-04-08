#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
CONFIG_DIR="${ROOT_DIR}/deploy/cloudflared"
CONFIG_FILE="${CONFIG_DIR}/config.yml"
CREDENTIALS_FILE="${CONFIG_DIR}/credentials.json"
TUNNEL_NAME="${1:-researchkit}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is required but not installed." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Create it from .env.example first." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

if [[ -z "${PUBLIC_DOMAIN:-}" ]]; then
  echo "PUBLIC_DOMAIN is not set in ${ENV_FILE}." >&2
  exit 1
fi

mkdir -p "${CONFIG_DIR}"

if [[ ! -f "${HOME}/.cloudflared/cert.pem" ]]; then
  echo "No Cloudflare origin cert found at ~/.cloudflared/cert.pem." >&2
  echo "Run: cloudflared tunnel login" >&2
  exit 1
fi

tmp_json="$(mktemp)"
trap 'rm -f "${tmp_json}"' EXIT

cloudflared tunnel create --credentials-file "${CREDENTIALS_FILE}" --output json "${TUNNEL_NAME}" > "${tmp_json}"

tunnel_id="$(
  python3 - "${tmp_json}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)

print(data["id"])
PY
)"

cat > "${CONFIG_FILE}" <<EOF
credentials-file: /etc/cloudflared/credentials.json

ingress:
  - hostname: ${PUBLIC_DOMAIN}
    service: http://nginx:8080
  - service: http_status:404
EOF

cloudflared tunnel route dns "${tunnel_id}" "${PUBLIC_DOMAIN}"

python3 - "${ENV_FILE}" "${tunnel_id}" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
tunnel_id = sys.argv[2]
lines = env_path.read_text(encoding="utf-8").splitlines()
updated = False

for idx, line in enumerate(lines):
    if line.startswith("CLOUDFLARE_TUNNEL_ID="):
        lines[idx] = f"CLOUDFLARE_TUNNEL_ID={tunnel_id}"
        updated = True
        break

if not updated:
    lines.append(f"CLOUDFLARE_TUNNEL_ID={tunnel_id}")

env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo
echo "Local tunnel created: ${tunnel_id}"
echo "Credentials written to: ${CREDENTIALS_FILE}"
echo "Config written to: ${CONFIG_FILE}"
echo "Updated ${ENV_FILE} with CLOUDFLARE_TUNNEL_ID"
echo
echo "Start it with:"
echo "  docker compose -f docker-compose.yml -f docker-compose.cloudflare.local.yml up -d --build"
