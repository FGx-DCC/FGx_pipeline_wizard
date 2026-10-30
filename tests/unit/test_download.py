"""Unit tests for file downloading."""

from io import BytesIO
from pathlib import Path
from typing import Self

import pytest

from pipeline_wizard.download import download_file


class _FakeResponse(BytesIO):
    def __enter__(self) -> Self:
        return self


@pytest.fixture
def fake_urlopen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fake the network, recording requested URLs."""
    requested: list[str] = []

    def opener(url: str, timeout: float | None = None) -> _FakeResponse:
        requested.append(url)
        return _FakeResponse(b"contents")

    monkeypatch.setattr("pipeline_wizard.download.urlopen", opener)
    return requested


@pytest.mark.parametrize(
    "url", ["http://x.org/f", "https://x.org/f", "ftp://x.org/f"]
)
def test_downloads_supported_schemes(
    tmp_path: Path, fake_urlopen: list[str], url: str
) -> None:
    """Should download http, https and ftp URLs to the destination.

    Given:
        A URL with a supported scheme and a destination file path.
    When:
        The file is downloaded.
    Then:
        The destination is returned and holds the downloaded bytes.

    """
    destination = tmp_path / "out.bin"

    result = download_file(url, destination, "default.bin")

    assert result == destination
    assert destination.read_bytes() == b"contents"
    assert fake_urlopen == [url]


def test_directory_destination_uses_default_name(
    tmp_path: Path, fake_urlopen: list[str]
) -> None:
    """Should place the file inside a directory under the default name.

    Given:
        A destination that is an existing directory.
    When:
        The file is downloaded.
    Then:
        The file is saved in it with the default file name.

    """
    result = download_file("https://x.org/f", tmp_path, "ref.fa")

    assert result == tmp_path / "ref.fa"
    assert result.read_bytes() == b"contents"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x", "nope"])
def test_rejects_unsupported_schemes(
    tmp_path: Path, fake_urlopen: list[str], url: str
) -> None:
    """Should refuse to fetch anything that isn't http(s)/ftp.

    Given:
        A URL with an unsupported scheme.
    When:
        The file is downloaded.
    Then:
        A ValueError is raised and nothing is requested.

    """
    with pytest.raises(ValueError, match="Unsupported scheme"):
        download_file(url, tmp_path / "out", "default")

    assert fake_urlopen == []
