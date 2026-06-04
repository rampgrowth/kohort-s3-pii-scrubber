#!/usr/bin/env bash
# First-time client bootstrap (run from repo root).
# 1. Creates client.yaml from the example if missing
# 2. Creates a Python venv and installs scripts/requirements.txt
#
# After this script: edit client.yaml for your account, then:
#   source .venv/bin/activate
#   python3 scripts/kohort_sanitize.py --config client.yaml setup
#   python3 scripts/kohort_sanitize.py --config client.yaml run --prefix '<your-prefix>' --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f client.yaml ]]; then
  cp scripts/client.yaml.example client.yaml
  echo "Created client.yaml from scripts/client.yaml.example"
  echo "→ Edit client.yaml (buckets, prefix, aws_profile, public_image tag) before setup."
else
  echo "Using existing client.yaml"
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  echo "Created .venv"
fi

.venv/bin/pip install -q -r scripts/requirements.txt
echo ""
echo "Ready. Next:"
echo "  source .venv/bin/activate"
echo "  # edit client.yaml if you have not already"
echo "  python3 scripts/kohort_sanitize.py --config client.yaml setup"
echo "    (default: CodeBuild mirrors image — no local Docker)"
echo "  python3 scripts/kohort_sanitize.py --config client.yaml setup --skip-image"
echo "  python3 scripts/kohort_sanitize.py --config client.yaml run --prefix '<prefix>' --dry-run"
