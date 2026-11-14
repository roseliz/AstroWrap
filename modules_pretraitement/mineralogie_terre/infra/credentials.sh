#!/usr/bin/env bash
# NASA Earthdata credentials -> two encrypted SSM parameters (SecureString, free), outside Terraform:
# they appear neither in user_data nor in the Terraform state. Nothing is printed.
#
#   ./credentials.sh create   reads .env at the repository root
#   ./credentials.sh delete   at the end of the work
export MSYS_NO_PATHCONV=1   # Git Bash (Windows): do not convert /mineralogie_terre/ into a file path
set -euo pipefail
# Repository root (three levels up); pwd -W gives the Windows path under Git Bash
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && (pwd -W 2>/dev/null || pwd))"
REGION=us-west-2
PREFIX=/mineralogie_terre/
case "${1:-}" in
  create)
    PY="$ROOT/.venv/Scripts/python.exe"; [[ -x "$PY" ]] || PY="$ROOT/.venv/bin/python"
    # Python reads .env and hands the values to aws through temporary files (never on the command line)
    "$PY" - "$ROOT" "$REGION" "$PREFIX" <<'EOF'
import os, subprocess, sys, tempfile
root, region, prefix = sys.argv[1:4]
values = {}
for line in open(os.path.join(root, ".env"), encoding="utf-8", errors="ignore"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, _, value = line.partition("=")
        values[key.strip().removeprefix("export ").strip()] = value.strip().strip("\"'")
user = values.get("EARTHDATA_USERNAME") or values.get("USERNAME_EARTHACCESS")
password = values.get("EARTHDATA_PASSWORD") or values.get("PASSWORD_EARTHACCESS")
if not (user and password):
    sys.exit(".env: Earthdata credentials not found")
for name, value in (("username", user), ("password", password)):
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(value)
    try:
        subprocess.run(["aws", "ssm", "put-parameter", "--region", region, "--name", prefix + name, "--type", "SecureString",
                        "--overwrite", "--value", "file://" + f.name, "--output", "text", "--query", "Version"],
                       check=True, stdout=subprocess.DEVNULL)
    finally:
        os.remove(f.name)
    print(f"parameter {prefix}{name} created (value not shown)")
EOF
    ;;
  delete)
    aws ssm delete-parameters --region "$REGION" --names "${PREFIX}username" "${PREFIX}password" \
      --query "{deleted:DeletedParameters,missing:InvalidParameters}" --output json ;;
  *) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
