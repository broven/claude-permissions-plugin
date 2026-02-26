"""Tests for add_permissions.py — global write, project cleanup, and log clearing."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parent.parent / "skills/permission-update/scripts/add_permissions.py")


def run_add(args: list[str], env_home: Path, cwd: Path, log_path: Path | None = None):
    """Run add_permissions.py in a subprocess with patched HOME and cwd."""
    import os

    env = os.environ.copy()
    env["HOME"] = str(env_home)
    # Patch the log file path via a small wrapper
    code = f"""
import sys, json
from pathlib import Path
# Patch hardcoded paths before the script's module-level code runs
import importlib.util
spec = importlib.util.spec_from_file_location("add_permissions", {SCRIPT!r})
mod = importlib.util.module_from_spec(spec)
# Override sys.argv
sys.argv = ["add_permissions.py"] + {args!r}
# We need to patch Path.home() and the log file path
_orig_home = Path.home
Path.home = classmethod(lambda cls: Path({str(env_home)!r}))
spec.loader.exec_module(mod)
"""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


class TestAddPermissions:
    def test_adds_to_global_settings(self, tmp_path):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        settings = claude_dir / "settings.json"
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}))

        project = tmp_path / "project"
        project.mkdir()

        result = run_add(["Bash(git add:*)"], home, project)
        assert result.returncode == 0

        data = json.loads(settings.read_text())
        assert "Bash(git add:*)" in data["permissions"]["allow"]
        assert "Bash(ls:*)" in data["permissions"]["allow"]

    def test_sorts_alphabetically_case_insensitive(self, tmp_path):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        settings = claude_dir / "settings.json"
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(npm:*)"]}}))

        project = tmp_path / "project"
        project.mkdir()

        result = run_add(["Bash(Apt:*)", "Bash(zsh:*)"], home, project)
        assert result.returncode == 0

        allow = json.loads(settings.read_text())["permissions"]["allow"]
        assert allow == sorted(allow, key=str.lower)

    def test_removes_from_project_settings_local(self, tmp_path):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(json.dumps({}))

        project = tmp_path / "project"
        proj_claude = project / ".claude"
        proj_claude.mkdir(parents=True)
        proj_settings = proj_claude / "settings.local.json"
        proj_settings.write_text(json.dumps({
            "permissions": {"allow": ["Bash(git add:*)", "Bash(cargo:*)"]}
        }))

        result = run_add(["Bash(git add:*)"], home, project)
        assert result.returncode == 0

        proj_allow = json.loads(proj_settings.read_text())["permissions"]["allow"]
        assert "Bash(git add:*)" not in proj_allow
        assert "Bash(cargo:*)" in proj_allow

    def test_clears_log_file(self, tmp_path):
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(json.dumps({}))

        project = tmp_path / "project"
        project.mkdir()

        # Create a fake log file at the real path (this test checks the actual behavior)
        log = Path("/tmp/bash-compound-allow.log")
        original_content = log.read_text() if log.exists() else None
        try:
            log.write_text("[10:00:00] PROMPT  | not in allow list: 'some cmd'\n")
            result = run_add(["Bash(test:*)"], home, project)
            assert result.returncode == 0
            assert log.read_text() == ""
            assert "Cleared" in result.stdout
        finally:
            # Restore original content
            if original_content is not None:
                log.write_text(original_content)
            elif log.exists():
                log.unlink()

    def test_no_args_exits_with_error(self, tmp_path):
        home = tmp_path / "home"
        project = tmp_path / "project"
        project.mkdir()
        result = run_add([], home, project)
        assert result.returncode == 1
