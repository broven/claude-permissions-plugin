# Fix permission-update duplicate suggestions

## Problem

Running `/permission-update` repeatedly shows duplicate and already-handled suggestions:
1. Log file `/tmp/bash-compound-allow.log` never gets cleared, so rejected commands reappear every run.
2. `analyze_log.py` dedup logic compares `first_word` against global pattern prefixes — mismatches when patterns are multi-word (e.g. `Bash(git add:*)` vs first_word `git`).
3. Grouping by `first_word` is too coarse — lumps all `git` subcommands into one `Bash(git:*)` suggestion.

## Changes

### 1. `scripts/analyze_log.py` — fix matching and grouping

- **Match check**: use fnmatch to test the full command against every existing global `Bash(...)` pattern. If any pattern matches, skip the command.
- **Grouping**: group by the first two words (e.g. `git add`, `npm run`). Single-word commands group by themselves.
- **Pattern generation**: if a group has >=2 records with different arguments, suggest `Bash(prefix:*)`. Otherwise suggest `Bash(exact_command)`.

### 2. `scripts/add_permissions.py` — clear log after write

After successfully writing to global settings, truncate `/tmp/bash-compound-allow.log` to empty.

### 3. `SKILL.md` — update step 5 description

Note that the log file is automatically cleared after permissions are written.

## Scope

3 files modified, 0 files added.
