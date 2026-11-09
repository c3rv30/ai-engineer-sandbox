"""Regression of the file name on ingestion (SEC-04).

The client controls the name. With '../' the file was written, and the finally deleted
it, outside the temporary directory; now only its last component is kept as metadata.
"""
import pytest

from src.services.filenames import source_name


@pytest.mark.parametrize("sent, expected", [
    ("cv.pdf", "cv.pdf"),
    ("../../etc/passwd.txt", "passwd.txt"),
    ("/var/folders/v2/T/cv.txt", "cv.txt"),
    ("..\\..\\Windows\\win.ini.md", "win.ini.md"),
    ("folder/sub\\mixed/../report.pdf", "report.pdf"),
    ("name with spaces.md", "name with spaces.md"),
])
def test_only_the_last_component(sent, expected):
    assert source_name(sent) == expected


@pytest.mark.parametrize("sent", ["../../etc/passwd.txt", "..\\secret.txt", "/abs/path.md", "a/../b.pdf"])
def test_no_separators_or_path_components(sent):
    result = source_name(sent)
    assert "/" not in result and "\\" not in result and result not in ("..", ".")
