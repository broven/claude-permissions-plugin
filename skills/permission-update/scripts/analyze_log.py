#!/usr/bin/env python3
"""
Analyze /tmp/bash-compound-allow.log to find commands that triggered permission prompts.
Groups by first word (command), counts frequency, and suggests Bash(cmd:*) allow patterns.
Output: JSON with suggestions list, sorted by frequency descending.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LOG_FILE = Path("/tmp/bash-compound-allow.log")

if not LOG_FILE.exists():
    print(json.dumps({"suggestions": [], "error": "Log file not found: /tmp/bash-compound-allow.log"}))
    sys.exit(0)

# Parse PROMPT lines: [HH:MM:SS] PROMPT  | not in allow list: 'cmd args'
pattern = re.compile(r"PROMPT\s+\|\s+not in allow list:\s+'(.+)'$")

counts: dict[str, int] = defaultdict(int)
examples: dict[str, list[str]] = defaultdict(list)

for line in LOG_FILE.read_text().splitlines():
    m = pattern.search(line)
    if not m:
        continue
    cmd = m.group(1).strip()
    # Strip redirections like 2>/dev/null for grouping purposes
    cmd_clean = re.sub(r"\s+\d*>.*$", "", cmd).strip()
    first_word = cmd_clean.split()[0] if cmd_clean.split() else cmd_clean
    counts[first_word] += 1
    if len(examples[first_word]) < 3:
        examples[first_word].append(cmd_clean)

# Read existing global allow to skip already-added patterns
global_settings = Path.home() / ".claude/settings.json"
existing = set()
try:
    data = json.loads(global_settings.read_text())
    for p in data.get("permissions", {}).get("allow", []):
        if p.startswith("Bash(") and p.endswith(")"):
            existing.add(p[5:-1].split(":")[0])  # extract command prefix
except Exception:
    pass

suggestions = []
for cmd, count in sorted(counts.items(), key=lambda x: -x[1]):
    if cmd in existing:
        continue  # already allowed
    suggestions.append({
        "pattern": f"Bash({cmd}:*)",
        "count": count,
        "examples": examples[cmd],
    })

print(json.dumps({"suggestions": suggestions}, ensure_ascii=False))
