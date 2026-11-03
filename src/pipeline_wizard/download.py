"""Methods to download files."""

from shutil import copyfileobj
from urllib.parse import urlparse
from urllib.request import urlopen

from pipeline_wizard.types import AbsolutePath


def download_file(
    url: str, destination: AbsolutePath, default_file_name: str
) -> AbsolutePath:
    """Attempt to download a file to some path."""
    if destination.is_dir():
        destination = destination / default_file_name

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", "ftp"):
        raise ValueError(
            f"Unsupported scheme for downloading: {parsed.scheme!r}"
        )

    with (
        urlopen(url, timeout=30) as response,
        open(destination, "wb") as out_file,
    ):
        copyfileobj(response, out_file)

    return destination
