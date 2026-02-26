#!/usr/bin/env python3
"""
Analyze /tmp/bash-compound-allow.log to find commands that triggered permission prompts.
Groups by command prefix (first two words or single-word command), counts frequency,
and suggests Bash(...) allow patterns.
Output: JSON with suggestions list, sorted by frequency descending.
"""
import fnmatch
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LOG_FILE = Path("/tmp/bash-compound-allow.log")
LINE_PATTERN = re.compile(r"PROMPT\s+\|\s+not in allow list:\s+['\"](.+)['\"]$")


def matches_pattern(cmd: str, pattern: str) -> bool:
    """Check if a command matches a Bash allow pattern (same logic as the hook)."""
    cmd = cmd.strip()
    if not cmd:
        return True
    if pattern == "*":
        return True
    if ":" in pattern:
        colon_idx = pattern.index(":")
        cmd_prefix = pattern[:colon_idx]
        args_pattern = pattern[colon_idx + 1:]
        if cmd == cmd_prefix:
            return fnmatch.fnmatch("", args_pattern)
        if cmd.startswith(cmd_prefix + " "):
            remaining = cmd[len(cmd_prefix) + 1:]
            return fnmatch.fnmatch(remaining, args_pattern)
        return False
    return fnmatch.fnmatch(cmd, pattern)


def command_prefix(cmd: str) -> str:
    """Extract grouping key: first two words for multi-word commands, or the single word."""
    words = cmd.split()
    if len(words) >= 2:
        return f"{words[0]} {words[1]}"
    return words[0] if words else cmd


def load_existing_patterns(global_settings_path: Path) -> list[str]:
    """Read existing Bash allow patterns from global settings."""
    try:
        data = json.loads(global_settings_path.read_text())
        return [
            p[5:-1]
            for p in data.get("permissions", {}).get("allow", [])
            if isinstance(p, str) and p.startswith("Bash(") and p.endswith(")")
        ]
    except Exception:
        return []


def analyze(log_path: Path, existing_patterns: list[str]) -> dict:
    """Parse log file and return suggestions dict."""
    if not log_path.exists():
        return {"suggestions": [], "error": f"Log file not found: {log_path}"}

    groups: dict[str, list[str]] = defaultdict(list)

    for line in log_path.read_text().splitlines():
        m = LINE_PATTERN.search(line)
        if not m:
            continue
        cmd = m.group(1).strip()
        cmd_clean = re.sub(r"\s+\d*>.*$", "", cmd).strip()
        if not cmd_clean:
            continue
        if any(matches_pattern(cmd_clean, pat) for pat in existing_patterns):
            continue
        prefix = command_prefix(cmd_clean)
        groups[prefix].append(cmd_clean)

    suggestions = []
    for prefix, cmds in sorted(groups.items(), key=lambda x: -len(x[1])):
        unique_cmds = list(dict.fromkeys(cmds))
        unique_args = set()
        for c in unique_cmds:
            rest = c[len(prefix):].strip()
            unique_args.add(rest)
        if len(unique_args) >= 2 or (len(unique_args) == 1 and "" not in unique_args):
            pattern = f"Bash({prefix}:*)"
        else:
            pattern = f"Bash({prefix})"
        suggestions.append({
            "pattern": pattern,
            "count": len(cmds),
            "examples": unique_cmds[:3],
        })

    return {"suggestions": suggestions}


if __name__ == "__main__":
    existing = load_existing_patterns(Path.home() / ".claude/settings.json")
    result = analyze(LOG_FILE, existing)
    print(json.dumps(result, ensure_ascii=False))
