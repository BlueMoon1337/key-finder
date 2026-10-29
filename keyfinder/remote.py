"""Importing songs from public URLs (cloud storage share links, direct file links).

The server fetches arbitrary user-supplied URLs, so requests are limited to
http(s) on public addresses (checked again on every redirect) to keep the
importer from reaching services on the host's private network.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path

TIMEOUT = 30
USER_AGENT = "KeyFinder/0.1"
STREAMING_HOSTS = ("youtube.com", "youtu.be", "spotify.com", "music.apple.com", "soundcloud.com", "tidal.com")


class UrlImportError(ValueError):
    """The URL cannot be imported; the message is safe to show to the user."""


def _rewrite_share_link(url: str) -> str:
    """Turn common cloud-storage share pages into direct-download links."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    if host.endswith("dropbox.com"):
        query = dict(urllib.parse.parse_qsl(parts.query))
        query["dl"] = "1"
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    if host == "drive.google.com":
        match = re.search(r"/file/d/([^/]+)", parts.path)
        file_id = match.group(1) if match else dict(urllib.parse.parse_qsl(parts.query)).get("id")
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={urllib.parse.quote(file_id)}"
    return url


def check_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UrlImportError("enter an http:// or https:// link")
    host = parts.hostname.lower()
    if any(host == h or host.endswith("." + h) for h in STREAMING_HOSTS):
        raise UrlImportError("streaming links won't work; use a link to the audio or video file itself")
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UrlImportError(f"could not resolve {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise UrlImportError("links to private or local network addresses are not allowed")
    return url.strip()


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _filename(response, url: str) -> str:
    header = response.headers.get("Content-Disposition", "")
    if header:
        msg = Message()
        msg["content-disposition"] = header
        name = msg.get_filename()
        if name:
            return Path(name).name
    name = Path(urllib.parse.unquote(urllib.parse.urlsplit(response.geturl() or url).path)).name
    return name or "Imported song"


def download(url: str, dest: Path, max_bytes: int) -> str:
    """Fetch ``url`` into ``dest``; returns a filename for the song."""
    url = check_url(_rewrite_share_link(url))
    opener = urllib.request.build_opener(_SafeRedirects)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            content_type = response.headers.get("Content-Type", "")
            if content_type.startswith("text/html"):
                raise UrlImportError("that link opens a web page, not a media file; use a direct download link")
            size = 0
            with open(dest, "wb") as out:
                while chunk := response.read(1 << 20):
                    size += len(chunk)
                    if size > max_bytes:
                        raise UrlImportError(f"file is larger than {max_bytes // (1024 * 1024)} MB")
                    out.write(chunk)
            if size == 0:
                raise UrlImportError("the link returned an empty file")
            return _filename(response, url)
    except UrlImportError:
        raise
    except OSError as exc:  # URLError, HTTPError, timeouts
        raise UrlImportError(f"download failed: {getattr(exc, 'reason', exc)}") from exc
