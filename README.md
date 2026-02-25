# claude-permissions-plugin

A Claude Code plugin for managing Bash permissions efficiently.

## Features

### 1. Hook: `bash-compound-allow`

Automatically approves compound Bash commands (joined with `&&`, `||`, `;`, `|`, or newlines) when **every individual part** matches your existing `allow` rules — no more per-prompt interruptions.

**Solves:** [anthropics/claude-code#16561](https://github.com/anthropics/claude-code/issues/16561)

- Reads allow rules from all settings files (`~/.claude/settings.json`, `~/.claude/settings.local.json`, `.claude/settings.json`, `.claude/settings.local.json`)
- Shell builtins (`echo`, `printf`, `cd`, etc.) and variable assignments are auto-allowed
- Logs every decision to `/tmp/bash-compound-allow.log`
- When a part is **not** allowed, shows a `systemMessage` identifying the exact command
- **Note:** In subagent contexts the hook still fires and enforces rules, but the `systemMessage` is not surfaced to the user — check `/tmp/bash-compound-allow.log` to see what was blocked

### 2. Skill: `/permission-update`

Collects allow rule candidates from two sources and lets you pick which to promote to global settings:

- **Source A — project settings:** rules in `.claude/settings.local.json` not yet in global `~/.claude/settings.json`
- **Source B — hook log:** commands that triggered prompts, ranked by frequency

Run periodically to keep your allow list up to date.

## Installation

### From GitHub (recommended)

In Claude Code, run these two commands:

```
/plugin marketplace add broven/claude-permissions-plugin
/plugin install claude-permissions-plugin@broven-claude-permissions-plugin
```
To install for a specific project only (shared with collaborators via `.claude/settings.json`):

```
/plugin install claude-permissions-plugin@broven-claude-permissions-plugin --scope project
```

### From a local clone

```bash
git clone https://github.com/broven/claude-permissions-plugin.git
```

Then in Claude Code:

```
/plugin marketplace add ./claude-permissions-plugin
/plugin install claude-permissions-plugin@claude-permissions-plugin
```


## Log

All hook decisions are written to `/tmp/bash-compound-allow.log`:

```
[14:23:01] APPROVE | parts: ['npm install', 'echo "done"']
[14:23:05] PROMPT  | not in allow list: 'unknowncmd foo'
```

Use `/permission-update` to turn PROMPT entries into allow rules.
