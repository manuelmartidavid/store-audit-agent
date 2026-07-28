"""Minimal .env loader — spec §2 secret handling."""

from __future__ import annotations

from crawler.dotenv import load


def test_basic_key_value_pairs_are_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("TSCC_PASSWORD", raising=False)
    env = tmp_path / ".env"
    env.write_text("TSCC_PASSWORD=hunter2\nOTHER=x\n", encoding="utf-8")

    applied = load(env)
    import os

    assert os.environ["TSCC_PASSWORD"] == "hunter2"
    assert set(applied) == {"TSCC_PASSWORD", "OTHER"}


def test_the_real_environment_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TSCC_PASSWORD", "from-shell")
    env = tmp_path / ".env"
    env.write_text("TSCC_PASSWORD=from-file\n", encoding="utf-8")

    applied = load(env)
    import os

    assert os.environ["TSCC_PASSWORD"] == "from-shell"
    assert "TSCC_PASSWORD" not in applied


def test_comments_blank_lines_export_and_quotes(tmp_path, monkeypatch):
    for key in ("A", "B", "C", "D"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n\nexport A=1\nB=\"two words\"\nC='single'\nD=has#hash\n",
        encoding="utf-8",
    )

    load(env)
    import os

    assert os.environ["A"] == "1"
    assert os.environ["B"] == "two words"
    assert os.environ["C"] == "single"
    assert os.environ["D"] == "has#hash", "a # inside a value is not a comment"


def test_the_loader_returns_names_never_values(tmp_path, monkeypatch):
    """The return value is logged; it must never carry a secret."""
    monkeypatch.delenv("TSCC_PASSWORD", raising=False)
    env = tmp_path / ".env"
    env.write_text("TSCC_PASSWORD=super-secret\n", encoding="utf-8")

    applied = load(env)
    assert applied == ["TSCC_PASSWORD"]
    assert "super-secret" not in "".join(applied)


def test_a_missing_env_file_is_not_an_error(tmp_path):
    assert load(tmp_path / "nope.env") == []
