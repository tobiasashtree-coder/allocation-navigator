"""Kleiner HTTP-Client mit Wiederholungen, Wartezeiten und Ratenbegrenzung.

Alle Provider greifen über diese Klasse auf das Netz zu. Dadurch lassen sich die
Provider in Tests mit einem Ersatz-Client ohne Netzzugriff prüfen.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

USER_AGENT = "allocation-navigator/0.1 (private, nicht-kommerzielle Nutzung)"


class HttpError(RuntimeError):
    """Fehler beim Abruf einer URL."""

    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class HttpResponse:
    """Antwort eines Abrufs."""

    status_code: int
    content: bytes
    url: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Inhalt als Text (UTF-8, ersatzweise Latin-1)."""
        try:
            return self.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return self.content.decode("latin-1")

    def json(self) -> Any:
        """Inhalt als JSON."""
        return json.loads(self.text)


class HttpClient:
    """HTTP-GET mit Wiederholung bei 429/5xx und Mindestabstand je Host."""

    def __init__(
        self,
        timeout: float = 45.0,
        retries: int = 3,
        backoff: float = 2.0,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})
        self._last_call: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

    def _throttle(self, host: str, min_interval: float) -> None:
        if min_interval <= 0:
            return
        wait = self._last_call.get(host, 0.0) + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        min_interval: float = 0.0,
    ) -> HttpResponse:
        """Ruft ``url`` ab. Wirft :class:`HttpError`, wenn der Abruf endgültig scheitert."""
        host = urlparse(url).netloc
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle(host, min_interval)
            try:
                resp = self._session.get(url, params=params, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                self._last_call[host] = time.monotonic()
            else:
                self._last_call[host] = time.monotonic()
                if resp.status_code == 200:
                    return HttpResponse(
                        status_code=200,
                        content=resp.content,
                        url=resp.url,
                        headers=dict(resp.headers),
                    )
                body = resp.text[:2000]
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise HttpError(
                        f"HTTP {resp.status_code} für {url}", status=resp.status_code, body=body
                    )
                last_error = HttpError(
                    f"HTTP {resp.status_code} für {url}", status=resp.status_code, body=body
                )
            if attempt < self.retries:
                time.sleep(self.backoff * (2**attempt))
        if isinstance(last_error, HttpError):
            raise last_error
        raise HttpError(f"Abruf gescheitert für {url}: {last_error}")

    def robots_allowed(self, url: str) -> bool:
        """Prüft ``robots.txt`` der Seite. Im Zweifel (nicht lesbar) gilt: nicht erlaubt."""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            parser: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
            try:
                text = self.get(f"{base}/robots.txt").text
                assert parser is not None
                parser.parse(text.splitlines())
            except (HttpError, AssertionError):
                parser = None
            self._robots[base] = parser
        cached = self._robots[base]
        return bool(cached and cached.can_fetch(USER_AGENT, url))
