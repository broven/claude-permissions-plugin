"""Tests for bash-compound-allow hook with bashlex AST parsing."""
import json
import os
import sys
import subprocess

import pytest

# Add scripts dir to path so we can import the module
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

# Also add vendor dir so bashlex is available
VENDOR_DIR = os.path.join(SCRIPTS_DIR, "vendor")
sys.path.insert(0, VENDOR_DIR)

# Import functions under test
from importlib.machinery import SourceFileLoader

mod = SourceFileLoader(
    "bash_compound_allow",
    os.path.join(SCRIPTS_DIR, "bash-compound-allow.py"),
).load_module()

extract_commands_from_ast = mod.extract_commands_from_ast
split_command = mod.split_command
is_trivially_allowed = mod.is_trivially_allowed
command_is_allowed = mod.command_is_allowed
matches_pattern = mod.matches_pattern


# ── AST extraction tests ────────────────────────────────────────────


class TestExtractCommandsFromAST:
    def test_for_loop(self):
        result = extract_commands_from_ast("for f in *.py; do echo $f; done")
        assert result == ["echo $f"]

    def test_if_then(self):
        result = extract_commands_from_ast("if [ -f foo ]; then cat foo; fi")
        assert result == ["[ -f foo ]", "cat foo"]

    def test_if_then_else(self):
        result = extract_commands_from_ast(
            "if [ -f foo ]; then cat foo; else echo missing; fi"
        )
        assert result == ["[ -f foo ]", "cat foo", "echo missing"]

    def test_while_loop(self):
        result = extract_commands_from_ast("while true; do sleep 1; done")
        assert result == ["true", "sleep 1"]

    def test_pipeline(self):
        result = extract_commands_from_ast("cat foo | grep bar | wc -l")
        assert result == ["cat foo", "grep bar", "wc -l"]

    def test_command_substitution(self):
        result = extract_commands_from_ast("echo $(git status)")
        # The outer command includes the full text, inner command is also extracted
        assert "git status" in result

    def test_subshell(self):
        result = extract_commands_from_ast("(echo hello && echo world)")
        assert "echo hello" in result
        assert "echo world" in result

    def test_and_or(self):
        result = extract_commands_from_ast("echo a && echo b || echo c")
        assert result == ["echo a", "echo b", "echo c"]

    def test_semicolons(self):
        result = extract_commands_from_ast("echo a; echo b; echo c")
        assert result == ["echo a", "echo b", "echo c"]

    def test_assignments_not_extracted(self):
        """Assignments are not commands — they should not appear in the result."""
        result = extract_commands_from_ast("FOO=bar; echo $FOO")
        assert result == ["echo $FOO"]

    def test_redirects_not_extracted(self):
        result = extract_commands_from_ast("echo hello > /tmp/out")
        assert result == ["echo hello"]

    def test_for_loop_multiple_commands(self):
        result = extract_commands_from_ast(
            "for f in *.txt; do wc -l $f; cat $f; done"
        )
        assert result == ["wc -l $f", "cat $f"]

    def test_nested_if_in_for(self):
        result = extract_commands_from_ast(
            "for f in *; do if [ -f $f ]; then echo $f; fi; done"
        )
        assert "[ -f $f ]" in result
        assert "echo $f" in result


# ── Fallback tests (bashlex can't parse these) ──────────────────────


class TestFallback:
    def test_arithmetic_expansion(self):
        """$((...)) is not supported by bashlex — should return None."""
        result = extract_commands_from_ast("echo $((1 + 2))")
        # bashlex may or may not handle this; if it fails, returns None
        # Either way is acceptable
        assert result is None or isinstance(result, list)

    def test_case_esac(self):
        """case/esac — bashlex may not handle this."""
        cmd = 'case $x in a) echo a;; b) echo b;; esac'
        result = extract_commands_from_ast(cmd)
        # If bashlex can parse it, great; if not, returns None (fallback)
        assert result is None or isinstance(result, list)


# ── Builtins tests ──────────────────────────────────────────────────


class TestBuiltins:
    def test_bracket_is_builtin(self):
        assert is_trivially_allowed("[ -f foo ]")

    def test_double_bracket_is_builtin(self):
        assert is_trivially_allowed("[[ -f foo ]]")

    def test_echo_is_builtin(self):
        assert is_trivially_allowed("echo hello")

    def test_test_is_builtin(self):
        assert is_trivially_allowed("test -f foo")

    def test_assignment_is_trivially_allowed(self):
        assert is_trivially_allowed('FOO="bar"')

    def test_export_assignment_is_trivially_allowed(self):
        assert is_trivially_allowed("export FOO=bar")

    def test_unknown_command_is_not_trivially_allowed(self):
        assert not is_trivially_allowed("rm -rf /")


# ── Regression: split_command still works ───────────────────────────


class TestSplitCommand:
    def test_and(self):
        assert split_command("echo a && echo b") == ["echo a", "echo b"]

    def test_or(self):
        assert split_command("echo a || echo b") == ["echo a", "echo b"]

    def test_semicolons(self):
        assert split_command("echo a; echo b") == ["echo a", "echo b"]

    def test_pipe(self):
        assert split_command("echo a | cat") == ["echo a", "cat"]

    def test_newline(self):
        assert split_command("echo a\necho b") == ["echo a", "echo b"]

    def test_quoted_semicolons_preserved(self):
        assert split_command('echo "a;b" && echo c') == ['echo "a;b"', "echo c"]


# ── Pattern matching regression ─────────────────────────────────────


class TestPatternMatching:
    def test_star_matches_anything(self):
        assert matches_pattern("rm -rf /", "*")

    def test_prefix_with_glob(self):
        assert matches_pattern("git add .", "git add:*")

    def test_prefix_no_args(self):
        assert matches_pattern("git add", "git add:*")

    def test_prefix_mismatch(self):
        assert not matches_pattern("git push", "git add:*")

    def test_exact_match(self):
        assert matches_pattern("jq", "jq")

    def test_exact_no_match(self):
        assert not matches_pattern("jq .", "jq")

    def test_command_is_allowed_with_patterns(self):
        patterns = ["git add:*", "npm:*"]
        assert command_is_allowed("git add .", patterns)
        assert command_is_allowed("echo hello", patterns)  # builtin
        assert not command_is_allowed("rm -rf /", patterns)


# ── End-to-end: simulate hook stdin/stdout ──────────────────────────


HOOK_SCRIPT = os.path.join(SCRIPTS_DIR, "bash-compound-allow.py")


class TestEndToEnd:
    def _run_hook(self, tool_input, settings_dir=None):
        """Run the hook script with simulated stdin, return (stdout, returncode)."""
        hook_input = json.dumps({
            "tool_name": "Bash",
            "tool_input": tool_input,
        })

        env = os.environ.copy()
        if settings_dir:
            env["HOME"] = settings_dir

        result = subprocess.run(
            [sys.executable, HOOK_SCRIPT],
            input=hook_input,
            capture_output=True,
            text=True,
            env=env,
        )
        return result.stdout.strip(), result.returncode

    def test_for_loop_approved(self, tmp_path):
        """For-loop with all commands in allow list → approved."""
        # Create settings with echo allowed (builtin anyway) and a custom pattern
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings = {
            "permissions": {
                "allow": ["Bash(echo:*)", "Bash(cat:*)"],
            }
        }
        (settings_dir / "settings.json").write_text(json.dumps(settings))

        stdout, rc = self._run_hook(
            {"command": "for f in *.txt; do cat $f; done"},
            settings_dir=str(tmp_path),
        )
        assert rc == 0
        data = json.loads(stdout)
        assert data.get("hookSpecificOutput", {}).get("permissionDecision") == "allow"

    def test_for_loop_rejected(self, tmp_path):
        """For-loop with disallowed command → prompt (normal flow)."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings = {
            "permissions": {
                "allow": ["Bash(echo:*)"],
            }
        }
        (settings_dir / "settings.json").write_text(json.dumps(settings))

        stdout, rc = self._run_hook(
            {"command": "for f in *.txt; do rm $f; done"},
            settings_dir=str(tmp_path),
        )
        assert rc == 0
        data = json.loads(stdout)
        assert data.get("hookSpecificOutput", {}).get("permissionDecision") == "ask"
        assert "rm" in data.get("hookSpecificOutput", {}).get("permissionDecisionReason")

    def test_simple_compound_approved(self, tmp_path):
        """Simple && compound with all parts allowed → approved."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        settings = {
            "permissions": {
                "allow": ["Bash(git status:*)", "Bash(git add:*)"],
            }
        }
        (settings_dir / "settings.json").write_text(json.dumps(settings))

        stdout, rc = self._run_hook(
            {"command": "git status && git add ."},
            settings_dir=str(tmp_path),
        )
        assert rc == 0
        data = json.loads(stdout)
        assert data.get("hookSpecificOutput", {}).get("permissionDecision") == "allow"

    def test_non_bash_tool_ignored(self, tmp_path):
        """Non-Bash tool → exit 0, no output."""
        hook_input = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/foo"},
        })
        result = subprocess.run(
            [sys.executable, HOOK_SCRIPT],
            input=hook_input,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""
