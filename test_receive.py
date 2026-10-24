"""Exercise checksum, extraction and build identity boundaries."""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from receive import ORIGIN, download, receive, unpack

BUILD = "11111111-1111-1111-1111-111111111111"


def archive(name: str = "index.html", *, link: bool = False) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as output:
        entry = tarfile.TarInfo(name)
        if link:
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/tmp"
            output.addfile(entry)
        else:
            entry.size = 5
            output.addfile(entry, io.BytesIO(b"hello"))
    return buffer.getvalue()


class ReceiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "public"

    def test_download_identifies_client_and_limits_response(self) -> None:
        response = Mock(url=ORIGIN + "lucid-pages.json")
        response.read.return_value = b"{}"
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch("receive.urlopen", return_value=context) as open_url:
            self.assertEqual(download("lucid-pages.json", 8192), b"{}")
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "LucidPagesMirror/1.0")
        response.read.assert_called_once_with(8193)

    def test_valid_snapshot_and_no_stale_merge(self) -> None:
        raw = archive()
        unpack(raw, hashlib.sha256(raw).hexdigest(), self.destination)
        self.assertEqual((self.destination / "index.html").read_text(), "hello")
        with self.assertRaises(FileExistsError):
            unpack(raw, hashlib.sha256(raw).hexdigest(), self.destination)

    def test_digest_mismatch_leaves_no_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "checksum"):
            unpack(archive(), "0" * 64, self.destination)
        self.assertFalse(self.destination.exists())

    def test_traversal_symlink_and_git_rejected(self) -> None:
        for name, link in [("../escape", False), ("/index.html", False),
                           (".git/config", False), ("index.html", True)]:
            raw = archive(name, link=link)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Unsafe"):
                unpack(raw, hashlib.sha256(raw).hexdigest(), self.destination)
        self.assertFalse(self.destination.exists())

    def test_waits_for_exact_build_before_download(self) -> None:
        raw = archive()
        old = json.dumps({"build_id": "old"}).encode()
        current = json.dumps({"version": "1", "build_id": BUILD,
                              "mirror_url": "https://austery.github.io/lucid-space/",
                              "sha256": hashlib.sha256(raw).hexdigest()}).encode()
        with patch("receive.download", side_effect=[old, current, raw]) as fetch, \
                patch("receive.time.sleep"):
            receive(BUILD, self.destination)
        self.assertEqual(fetch.call_count, 3)
        self.assertTrue((self.destination / "index.html").is_file())

    def test_timeout_preserves_previous_site(self) -> None:
        with patch("receive.time.monotonic", side_effect=[0, 1201]), \
                self.assertRaisesRegex(ValueError, "20 minutes"):
            receive(BUILD, self.destination)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
