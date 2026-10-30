"""Tests for screener/project.py: the saved video source and its checks."""

import json
from pathlib import Path

import pytest

from screener.project import (
    probe_bucket,
    read_project,
    validate_bucket_url,
    validate_folder,
    write_project,
)
from tests.fakes3 import FakeS3


def test_project_round_trip(tmp_path: Path):
    write_project(tmp_path, "https://example.org", "videos/")
    assert read_project(tmp_path) == {"bucket_url": "https://example.org", "folder": "videos/"}
    assert [item.name for item in tmp_path.iterdir()] == ["project.json"]


def test_no_project_file_means_no_choice(tmp_path: Path):
    assert read_project(tmp_path) is None


@pytest.mark.parametrize(
    "text",
    ["{broken", "[]", "{}", '{"bucket_url": 3, "folder": "a/"}', '{"bucket_url": "ftp://x", "folder": "a/"}', '{"bucket_url": "https://x", "folder": ""}'],
)
def test_damaged_project_file_means_no_choice(tmp_path: Path, text: str):
    (tmp_path / "project.json").write_text(text, encoding="utf-8")
    assert read_project(tmp_path) is None


def test_bucket_url_is_trimmed():
    assert validate_bucket_url(" https://example.org/ ") == "https://example.org"


@pytest.mark.parametrize("bad", ["", "example.org", "ftp://example.org", "https://", "https://a.org/?x=1", "https://a.org#", "https://a.org?", "https://a b.org", 3, None])
def test_bad_bucket_url(bad):
    with pytest.raises(ValueError, match="^bucket_url"):
        validate_bucket_url(bad)


@pytest.mark.parametrize("given, wanted", [("videos", "videos/"), ("videos/", "videos/"), ("/a/b/", "a/b/"), (" a/b ", "a/b/")])
def test_folder_gets_one_trailing_slash(given, wanted):
    assert validate_folder(given) == wanted


@pytest.mark.parametrize("bad", ["", "/", "a/../b", "../a", "a//b", "a/./b", "a\nb", "x" * 600, 3, None])
def test_bad_folder(bad):
    with pytest.raises(ValueError, match="^folder"):
        validate_folder(bad)


@pytest.fixture
def bucket():
    server = FakeS3()
    server.start()
    server.put("videos/a.MP4", b"x")
    yield server
    server.stop()


def test_probe_finds_a_folder_with_videos(bucket):
    probe_bucket(bucket.url, "videos/")


def test_probe_refuses_an_empty_folder(bucket):
    with pytest.raises(ValueError, match="^folder"):
        probe_bucket(bucket.url, "nothing/")


def test_probe_refuses_a_dead_address():
    with pytest.raises(ValueError, match="^bucket_url"):
        probe_bucket("http://127.0.0.1:9", "videos/")


def test_probe_refuses_a_malformed_port():
    with pytest.raises(ValueError, match="^bucket_url"):
        probe_bucket("http://example.org:abc", "videos/")


def test_saved_file_is_plain_json(tmp_path: Path):
    write_project(tmp_path, "https://example.org", "videos/")
    assert json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))["folder"] == "videos/"
