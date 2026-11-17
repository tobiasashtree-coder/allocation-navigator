"""Gemeinsame Testhilfen: Projektpfade, Konfiguration und ein HTTP-Ersatz ohne Netz."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from navigator.config import AppConfig, load_config
from navigator.http import HttpError, HttpResponse
from navigator.paths import ProjectPaths

REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeHttp:
    """Ersatz für HttpClient: beantwortet URLs anhand von Teilstrings, zählt die Aufrufe."""

    def __init__(self, routes: dict[str, Any], robots: bool = True) -> None:
        self.routes = routes
        self.robots = robots
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        min_interval: float = 0.0,
    ) -> HttpResponse:
        self.calls.append((url, dict(params or {})))
        for fragment, answer in self.routes.items():
            if fragment in url:
                if isinstance(answer, Callable):  # type: ignore[arg-type]
                    answer = answer(url, dict(params or {}))
                if isinstance(answer, Exception):
                    raise answer
                if isinstance(answer, dict | list):
                    answer = json.dumps(answer)
                if isinstance(answer, str):
                    answer = answer.encode("utf-8")
                return HttpResponse(status_code=200, content=answer, url=url)
        raise HttpError(f"HTTP 404 für {url}", status=404)

    def robots_allowed(self, url: str) -> bool:
        return self.robots


@pytest.fixture(scope="session")
def config() -> AppConfig:
    """Die echte Projektkonfiguration."""
    return load_config(REPO_ROOT / "config")


@pytest.fixture()
def demo_paths(tmp_path: Path) -> ProjectPaths:
    """Leeres Projekt im Demo-Modus mit Kopie der Konfiguration."""
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    paths = ProjectPaths(root=tmp_path, demo=True)
    paths.ensure()
    return paths


@pytest.fixture(scope="session")
def demo_project(tmp_path_factory: pytest.TempPathFactory, config: AppConfig) -> ProjectPaths:
    """Einmal je Testlauf: Demo-Daten vollständig geladen."""
    from navigator.data.pipeline import update_data

    root = tmp_path_factory.mktemp("demo_project")
    shutil.copytree(REPO_ROOT / "config", root / "config")
    paths = ProjectPaths(root=root, demo=True)
    update_data(config, paths)
    return paths
