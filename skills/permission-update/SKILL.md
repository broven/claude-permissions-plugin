---
name: permission-update
disable-model-invocation: true
user-invocable: true
model: haiku
---

# permission-update

Collect allow rule candidates from two sources, let the user pick, and write them to global settings.

## Steps

### 1. Gather candidates from both sources (run in parallel)

**Source A — project settings:**
```bash
python3 <skill_dir>/scripts/find_new_permissions.py
```
Output: one `Bash(...)` permission per line, or `NONE`.

**Source B — hook log analysis:**
```bash
python3 <skill_dir>/scripts/analyze_log.py
```
Output: JSON `{"suggestions": [{"pattern": "Bash(sort:*)", "count": 9, "examples": [...]}, ...]}`

### 2. Build the combined candidate list

- From Source A: each line is a ready-to-add permission string.
- From Source B: each `suggestions[].pattern` is a candidate; append `×N` to the label so the user sees frequency.
- Deduplicate: skip B candidates already covered by A.
- If both sources are empty / NONE, inform the user and stop.

### 3. Ask the user (multiSelect)

Present all candidates in one or more `AskUserQuestion` calls (max 4 options each):
- Label format: `Bash(cmd:*)` or `Bash(cmd:*)  ×9 times`
- Description: source ("from project settings" or example commands from log)
- If user selects nothing, inform and stop.

### 4. Write selected permissions to global settings

```bash
python3 <skill_dir>/scripts/add_permissions.py "perm1" "perm2" ...
```
This merges + sorts alphabetically. It also removes promoted permissions from `.claude/settings.local.json`.

### 5. Confirm

Report what was added. The log file is automatically cleared after permissions are written.

## Notes

- `<skill_dir>` is the directory containing this SKILL.md.
- `add_permissions.py` only removes from project settings.local the items that came from Source A. Log-based suggestions have no project-local entry to clean up.
- Scripts never remove existing global permissions.
