"""Tests for analyze_log.py — pattern matching, grouping, and full analysis."""
import json
import sys
from pathlib import Path

import pytest

# Make the scripts importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills/permission-update/scripts"))
from analyze_log import analyze, command_prefix, matches_pattern


# ── matches_pattern ──────────────────────────────────────────────────────────


class TestMatchesPattern:
    def test_wildcard_matches_anything(self):
        assert matches_pattern("git push --force", "*") is True

    def test_exact_match(self):
        assert matches_pattern("jq", "jq") is True
        assert matches_pattern("jq .", "jq") is False

    def test_prefix_with_wildcard_args(self):
        assert matches_pattern("git add foo.txt", "git add:*") is True
        assert matches_pattern("git add", "git add:*") is True
        assert matches_pattern("git push origin", "git add:*") is False

    def test_single_word_prefix_with_wildcard(self):
        assert matches_pattern("npm install express", "npm:*") is True
        assert matches_pattern("npm", "npm:*") is True
        assert matches_pattern("npx create-app", "npm:*") is False

    def test_glob_without_colon(self):
        assert matches_pattern("ls -la", "ls*") is True
        assert matches_pattern("lsof", "ls*") is True

    def test_empty_command(self):
        assert matches_pattern("", "anything") is True
        assert matches_pattern("  ", "anything") is True


# ── command_prefix ───────────────────────────────────────────────────────────


class TestCommandPrefix:
    def test_two_words(self):
        assert command_prefix("git add foo.txt") == "git add"

    def test_single_word(self):
        assert command_prefix("jq") == "jq"

    def test_two_words_exact(self):
        assert command_prefix("npm install") == "npm install"

    def test_many_words(self):
        assert command_prefix("docker compose up -d") == "docker compose"


# ── analyze (full pipeline) ──────────────────────────────────────────────────


class TestAnalyze:
    def test_missing_log_file(self, tmp_path):
        result = analyze(tmp_path / "nonexistent.log", [])
        assert result["suggestions"] == []
        assert "error" in result

    def test_filters_already_covered_commands(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] PROMPT  | not in allow list: 'git add foo.txt'\n"
            "[10:00:01] PROMPT  | not in allow list: 'cargo build --release'\n"
        )
        # git add:* covers the first command, cargo is not covered
        result = analyze(log, ["git add:*"])
        patterns = [s["pattern"] for s in result["suggestions"]]
        assert "Bash(git add:*)" not in patterns
        assert any("cargo" in p for p in patterns)

    def test_ignores_approve_lines(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] APPROVE | parts: ['ls', 'echo done']\n"
            "[10:00:01] PROMPT  | not in allow list: 'cargo test unit'\n"
        )
        result = analyze(log, [])
        assert len(result["suggestions"]) == 1
        assert "cargo" in result["suggestions"][0]["pattern"]

    def test_groups_by_two_word_prefix(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] PROMPT  | not in allow list: 'git add foo.txt'\n"
            "[10:00:01] PROMPT  | not in allow list: 'git add bar.txt'\n"
            "[10:00:02] PROMPT  | not in allow list: 'git push origin main'\n"
        )
        result = analyze(log, [])
        patterns = {s["pattern"] for s in result["suggestions"]}
        # git add has two different args → wildcard
        assert "Bash(git add:*)" in patterns
        # git push has one entry with args → wildcard
        assert "Bash(git push:*)" in patterns
        # should NOT merge into a single Bash(git:*)
        assert "Bash(git:*)" not in patterns

    def test_exact_match_for_no_args_command(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] PROMPT  | not in allow list: 'htop'\n"
        )
        result = analyze(log, [])
        assert result["suggestions"][0]["pattern"] == "Bash(htop)"

    def test_wildcard_when_single_command_has_args(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] PROMPT  | not in allow list: 'rustup show active-toolchain'\n"
        )
        result = analyze(log, [])
        assert result["suggestions"][0]["pattern"] == "Bash(rustup show:*)"

    def test_sorted_by_frequency_descending(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] PROMPT  | not in allow list: 'make build'\n"
            "[10:00:01] PROMPT  | not in allow list: 'cargo test unit'\n"
            "[10:00:02] PROMPT  | not in allow list: 'cargo test integration'\n"
            "[10:00:03] PROMPT  | not in allow list: 'cargo test e2e'\n"
        )
        result = analyze(log, [])
        counts = [s["count"] for s in result["suggestions"]]
        assert counts == sorted(counts, reverse=True)

    def test_deduplicates_examples(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] PROMPT  | not in allow list: 'cargo build --release'\n"
            "[10:00:01] PROMPT  | not in allow list: 'cargo build --release'\n"
            "[10:00:02] PROMPT  | not in allow list: 'cargo build --debug'\n"
        )
        result = analyze(log, [])
        s = result["suggestions"][0]
        assert s["count"] == 3  # total occurrences
        assert s["examples"] == ["cargo build --release", "cargo build --debug"]

    def test_strips_redirections(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text(
            "[10:00:00] PROMPT  | not in allow list: 'mycmd --flag 2>/dev/null'\n"
            "[10:00:01] PROMPT  | not in allow list: 'mycmd --flag --verbose'\n"
        )
        result = analyze(log, [])
        s = result["suggestions"][0]
        assert s["pattern"] == "Bash(mycmd --flag:*)"
        # The redirection should be stripped from examples
        assert all(">/dev/null" not in e for e in s["examples"])
