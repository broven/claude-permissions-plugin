#!/usr/bin/env python3
"""
Add permissions to global ~/.claude/settings.json, sorted alphabetically (case-insensitive),
then remove those permissions from the project .claude/settings.local.json.
Usage: python3 add_permissions.py "perm1" "perm2" ...
"""
import json
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: add_permissions.py <perm1> [perm2 ...]", file=sys.stderr)
    sys.exit(1)

to_add = sys.argv[1:]
global_settings = Path.home() / ".claude/settings.json"
project_settings = Path(".claude/settings.local.json")

# --- Add to global settings ---
try:
    data = json.loads(global_settings.read_text()) if global_settings.exists() else {}
except json.JSONDecodeError as e:
    print(f"Error: {global_settings} is malformed JSON: {e}", file=sys.stderr)
    sys.exit(1)
allow = data.setdefault("permissions", {}).setdefault("allow", [])

merged = sorted(set(allow) | set(to_add), key=str.lower)
data["permissions"]["allow"] = merged

global_settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print(f"Added {len(to_add)} permission(s) to global. Total: {len(merged)}.")

# Clear the hook log so old entries don't reappear in future runs
log_file = Path("/tmp/bash-compound-allow.log")
if log_file.exists():
    log_file.write_text("")
    print("Cleared /tmp/bash-compound-allow.log.")

# --- Remove from project settings.local ---
if project_settings.exists():
    proj = json.loads(project_settings.read_text())
    proj_allow = proj.get("permissions", {}).get("allow", [])
    removed = [p for p in proj_allow if p in set(to_add)]
    if removed:
        proj["permissions"]["allow"] = sorted(
            [p for p in proj_allow if p not in set(to_add)], key=str.lower
        )
        project_settings.write_text(json.dumps(proj, indent=2, ensure_ascii=False) + "\n")
        print(f"Removed {len(removed)} permission(s) from project settings.local.")
