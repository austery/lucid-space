"""Receive only the public static snapshot produced by the requested build."""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import cast

ORIGIN = "https://lucid-blog.lucid-blog.workers.dev/.well-known/"
UUID = re.compile(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}")


def download(name: str, limit: int) -> bytes:
    request = Request(ORIGIN + name, headers={"Cache-Control": "no-cache", "User-Agent": "LucidPagesMirror/1.0"})
    with urlopen(request, timeout=30) as response:
        if response.url != ORIGIN + name:
            raise ValueError("Unexpected mirror download redirect")
        raw = cast(bytes, response.read(limit + 1))
    if len(raw) > limit:
        raise ValueError("Mirror download exceeds size limit")
    return raw


def unpack(raw: bytes, expected: str, destination: Path) -> None:
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Mirror archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 10000 or sum(m.size for m in members) > 100 * 1024 * 1024:
            raise ValueError("Mirror archive exceeds extracted size limit")
        names: set[str] = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or ".." in path.parts
                    or ".git" in path.parts or member.name in names):
                raise ValueError("Unsafe mirror archive entry")
            names.add(member.name)
        if "index.html" not in names:
            raise ValueError("Mirror archive has no homepage")
        destination.mkdir()  # Never merge with a stale output directory.
        for member in members:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Unreadable mirror archive entry")
            with stream:
                target.write_bytes(stream.read())
        (destination / ".nojekyll").write_text("")


def receive(build_id: str, destination: Path) -> None:
    if UUID.fullmatch(build_id) is None:
        raise ValueError("Invalid requested build ID")
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        try:
            value = cast(object, json.loads(download("lucid-pages.json", 8192)))
            if not isinstance(value, dict):
                raise ValueError("Invalid mirror receipt")
            if value.get("build_id") == build_id:
                expected = value.get("sha256")
                if (value.get("version") != "1"
                        or value.get("mirror_url") != "https://austery.github.io/lucid-space/"
                        or not isinstance(expected, str)
                        or re.fullmatch(r"[a-f0-9]{64}", expected) is None):
                    raise ValueError("Invalid mirror receipt")
                raw = download("lucid-pages.tar.gz", 24 * 1024 * 1024)
                # A concurrent later publication can replace the archive. Fail safely.
                unpack(raw, expected, destination)
                print("Verified public snapshot received: " + build_id)
                return
        except HTTPError as error:
            if error.code not in {404, 429, 500, 502, 503, 504}:
                raise ValueError(f"Mirror receipt returned HTTP {error.code}") from None
        except (URLError, TimeoutError):
            pass
        time.sleep(20)
    raise ValueError("Cloudflare did not publish this build within 20 minutes")


if __name__ == "__main__":
    try:
        request = json.loads(Path("trigger.json").read_text())
        receive(request["build_id"], Path("public"))
    except (ValueError, OSError, tarfile.TarError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
