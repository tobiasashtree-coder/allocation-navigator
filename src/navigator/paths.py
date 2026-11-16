"""Verzeichnisse des Projekts.

Alle Pfade leiten sich aus einem Projektwurzelverzeichnis ab. Es wird über die
Umgebungsvariable ``NAVIGATOR_HOME`` gesetzt; ohne sie gilt das erste übergeordnete
Verzeichnis des Arbeitsverzeichnisses, das einen Ordner ``config`` enthält.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """Liefert die Projektwurzel (Ordner mit ``config/``)."""
    env = os.environ.get("NAVIGATOR_HOME")
    if env:
        return Path(env).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "config" / "universe.yaml").exists():
            return candidate
    return here


@dataclass(frozen=True)
class ProjectPaths:
    """Bündelt alle Verzeichnisse eines Laufs.

    Im Demo-Modus liegen die Daten bewusst in einem eigenen Ordner (``data_demo``),
    damit synthetische Testdaten nie mit echten Daten vermischt werden.
    """

    root: Path
    demo: bool = False

    @property
    def config(self) -> Path:
        """Konfigurationsordner."""
        return self.root / "config"

    @property
    def data(self) -> Path:
        """Datenordner (nicht in Git)."""
        return self.root / ("data_demo" if self.demo else "data")

    @property
    def raw(self) -> Path:
        """Rohdaten-Cache je Quelle und Reihe."""
        return self.data / "raw"

    @property
    def static(self) -> Path:
        """Statische Downloads und manuell abgelegte Dateien."""
        return self.data / "static"

    @property
    def processed(self) -> Path:
        """Aufbereitete Daten (Point-in-Time-Speicher, Universum)."""
        return self.data / "processed"

    @property
    def pit(self) -> Path:
        """Point-in-Time-Speicher der Makroreihen."""
        return self.processed / "pit"

    @property
    def snapshots(self) -> Path:
        """Eingefrorene Datenstände."""
        return self.data / "snapshots"

    @property
    def runs(self) -> Path:
        """Laufprotokolle."""
        return self.data / "runs"

    @property
    def reports(self) -> Path:
        """Berichte (Validierung, später Monatsberichte)."""
        return self.root / ("reports_demo" if self.demo else "reports")

    def ensure(self) -> None:
        """Legt alle Datenverzeichnisse an."""
        for path in (self.raw, self.static, self.pit, self.snapshots, self.runs, self.reports):
            path.mkdir(parents=True, exist_ok=True)


def project_paths(root: Path | None = None, demo: bool = False) -> ProjectPaths:
    """Erzeugt die Pfade für die Projektwurzel ``root`` (Standard: automatisch gefunden)."""
    return ProjectPaths(root=root or find_project_root(), demo=demo)
