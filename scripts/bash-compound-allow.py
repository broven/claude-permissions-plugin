#!/usr/bin/env python3
"""
PreToolUse hook: auto-approve compound bash commands if every part matches allow rules.
Solves: https://github.com/anthropics/claude-code/issues/16561

Patterns like Bash(jq:*) or Bash(git add:*) are matched per-part.
If all parts are allowed → {"hookSpecificOutput": {"permissionDecision": "allow"}}
Otherwise → exit 0 (normal permission flow) with a systemMessage showing which part failed.
"""
import json
import sys
import re
import fnmatch
import os
from datetime import datetime

LOG_FILE = "/tmp/bash-compound-allow.log"


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    print(msg, file=sys.stderr)


def get_allow_patterns(settings_path):
    try:
        with open(settings_path) as f:
            data = json.load(f)
        patterns = []
        for p in data.get("permissions", {}).get("allow", []):
            if isinstance(p, str) and p.startswith("Bash(") and p.endswith(")"):
                patterns.append(p[5:-1])  # extract content inside Bash(...)
        return patterns
    except Exception:
        return []


def collect_all_patterns(cwd):
    """Read allow patterns from all settings files (global + project, including .local variants)."""
    candidates = [
        os.path.expanduser("~/.claude/settings.json"),
        os.path.expanduser("~/.claude/settings.local.json"),
        os.path.join(cwd, ".claude", "settings.json"),
        os.path.join(cwd, ".claude", "settings.local.json"),
    ]
    patterns = []
    for path in candidates:
        patterns.extend(get_allow_patterns(path))
    return patterns


def split_command(cmd):
    """Split compound command into parts, respecting single/double quotes."""
    parts = []
    current = []
    in_single = False
    in_double = False
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if c == "'" and not in_double:
            in_single = not in_single
            current.append(c)
        elif c == '"' and not in_single:
            in_double = not in_double
            current.append(c)
        elif not in_single and not in_double:
            two = cmd[i : i + 2]
            if two in ("&&", "||"):
                parts.append("".join(current).strip())
                current = []
                i += 1  # skip second char
            elif c in (";", "\n", "|"):
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(c)
        else:
            current.append(c)
        i += 1

    if current:
        parts.append("".join(current).strip())

    return [p for p in parts if p]


SHELL_BUILTINS = {
    "echo", "printf", "true", "false", "test", ":", ".",
    "cd", "pwd", "exit", "return", "export", "unset",
    "source", "read", "shift", "set",
}


def is_trivially_allowed(cmd):
    """Comments, variable assignments, and shell builtins are always safe."""
    cmd = cmd.strip()
    if not cmd:
        return True
    if cmd.startswith("#"):
        return True
    # e.g.  REQ_ID="abc"  or  export FOO=bar
    if re.match(r"^(export\s+)?[A-Za-z_][A-Za-z0-9_]*=", cmd):
        return True
    # Shell builtins: match first word
    first_word = cmd.split()[0] if cmd.split() else ""
    if first_word in SHELL_BUILTINS:
        return True
    return False


def matches_pattern(cmd, pattern):
    """
    Match a single command against one allow pattern.

    Pattern formats:
      *           → anything
      jq:*        → command starts with 'jq', any args
      git add:*   → command starts with 'git add', any args
      jq          → exact match (no colon → plain glob)
    """
    cmd = cmd.strip()
    if not cmd:
        return True
    if pattern == "*":
        return True

    if ":" in pattern:
        colon_idx = pattern.index(":")
        cmd_prefix = pattern[:colon_idx]
        args_pattern = pattern[colon_idx + 1 :]

        if cmd == cmd_prefix:
            return fnmatch.fnmatch("", args_pattern)
        if cmd.startswith(cmd_prefix + " "):
            remaining = cmd[len(cmd_prefix) + 1 :]
            return fnmatch.fnmatch(remaining, args_pattern)
        return False

    # No colon: plain glob against the full command string
    return fnmatch.fnmatch(cmd, pattern)


def command_is_allowed(cmd, patterns):
    if is_trivially_allowed(cmd):
        return True
    for pattern in patterns:
        if matches_pattern(cmd, pattern):
            return True
    return False


def main():
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")

    # Only bother with compound commands
    is_compound = "\n" in command or bool(re.search(r"&&|\|\||;", command))
    has_pipe = bool(re.search(r"(?<!\|)\|(?!\|)", command))
    if not is_compound and not has_pipe:
        sys.exit(0)

    # Load allow patterns (global + project, including .local variants)
    patterns = collect_all_patterns(os.getcwd())

    if not patterns:
        sys.exit(0)

    parts = split_command(command)
    if not parts:
        sys.exit(0)

    for part in parts:
        if not command_is_allowed(part, patterns):
            log(f"PROMPT  | not in allow list: {part!r}")
            print(json.dumps({
                "systemMessage": f"[bash-compound-allow] not in allow list: {part!r}",
            }))
            sys.exit(0)  # normal permission flow

    # Every part matched → approve
    log(f"APPROVE | parts: {parts}")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "✅ auto-approved by claude-permissions-plugin",
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
