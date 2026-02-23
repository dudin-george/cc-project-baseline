"""Tests for atomic file persistence."""

import json

import pytest

from mycroft.server.state.persistence import (
    atomic_json_write,
    json_read,
    jsonl_append,
    jsonl_read,
)


class TestAtomicJsonWrite:
    def test_write_creates_file(self, tmp_path):
        path = tmp_path / "test.json"
        atomic_json_write(path, {"key": "value"})
        assert path.exists()
        assert json.loads(path.read_text()) == {"key": "value"}

    def test_write_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "test.json"
        atomic_json_write(path, {"nested": True})
        assert path.exists()

    def test_write_overwrites(self, tmp_path):
        path = tmp_path / "test.json"
        atomic_json_write(path, {"v": 1})
        atomic_json_write(path, {"v": 2})
        assert json.loads(path.read_text()) == {"v": 2}

    def test_no_temp_file_left_on_success(self, tmp_path):
        path = tmp_path / "test.json"
        atomic_json_write(path, {"ok": True})
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.json"


class TestJsonRead:
    def test_read_valid(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"key": "value"}')
        assert json_read(path) == {"key": "value"}

    def test_read_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            json_read(tmp_path / "missing.json")

    def test_read_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            json_read(path)


class TestJsonlAppend:
    def test_append_creates_file(self, tmp_path):
        path = tmp_path / "log.jsonl"
        jsonl_append(path, {"msg": "first"})
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0]) == {"msg": "first"}

    def test_append_multiple(self, tmp_path):
        path = tmp_path / "log.jsonl"
        jsonl_append(path, {"n": 1})
        jsonl_append(path, {"n": 2})
        jsonl_append(path, {"n": 3})
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_append_creates_parents(self, tmp_path):
        path = tmp_path / "a" / "b" / "log.jsonl"
        jsonl_append(path, {"nested": True})
        assert path.exists()


class TestJsonlRead:
    def test_read_missing_returns_empty(self, tmp_path):
        assert jsonl_read(tmp_path / "missing.jsonl") == []

    def test_read_records(self, tmp_path):
        path = tmp_path / "log.jsonl"
        path.write_text('{"a": 1}\n{"a": 2}\n')
        records = jsonl_read(path)
        assert len(records) == 2
        assert records[0] == {"a": 1}
        assert records[1] == {"a": 2}

    def test_read_skips_blank_lines(self, tmp_path):
        path = tmp_path / "log.jsonl"
        path.write_text('{"a": 1}\n\n\n{"a": 2}\n')
        records = jsonl_read(path)
        assert len(records) == 2

    def test_read_empty_file(self, tmp_path):
        path = tmp_path / "log.jsonl"
        path.write_text("")
        assert jsonl_read(path) == []
