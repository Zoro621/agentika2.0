import io
import stat
import zipfile
import pytest
from claimbreaker.ingest import unpack, IntakeError, normalized_path


def archive(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in entries:
            z.writestr(k, v)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "path", ["../escape.py", "/root.py", "C:/escape.py", "foo/../../x.py", "foo\\..\\secret.py"]
)
def test_traversal_rejected(path):
    with pytest.raises(IntakeError):
        unpack("project.zip", archive([(path, "print(1)")]))


def test_secret_and_binary_exclusion():
    accepted, ignored = unpack(
        "project.zip",
        archive(
            [
                ("train.py", "x=1"),
                (".env", "SECRET=notreal"),
                ("node_modules/x.py", "x"),
                ("payload.exe", "x"),
                ("nested.zip", "not traversed"),
            ]
        ),
    )
    assert [p for p, _ in accepted] == ["train.py"]
    assert len(ignored) == 4


def test_duplicate_normalized_paths_rejected():
    with pytest.raises(IntakeError):
        unpack("project.zip", archive([("Train.py", "x"), ("train.py", "y")]))


def test_symlink_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        link = zipfile.ZipInfo("link.py")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, "/etc/passwd")
    with pytest.raises(IntakeError):
        unpack("project.zip", stream.getvalue())


def test_bomb_rejected():
    with pytest.raises(IntakeError):
        unpack("project.zip", archive([("data.csv", "x" * 2_000_000)]))


def test_invalid_input():
    with pytest.raises(IntakeError):
        unpack("file.zip", b"not a zip")
    with pytest.raises(IntakeError):
        unpack("file.exe", b"content")
