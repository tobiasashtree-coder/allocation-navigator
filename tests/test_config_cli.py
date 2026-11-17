"""M0: Konfiguration und Kommandozeile."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from navigator.cli import app
from navigator.config import QUADRANTS, AppConfig, Segment, config_hash, load_config
from tests.conftest import REPO_ROOT

runner = CliRunner()


def test_config_loads_with_18_asset_classes(config: AppConfig) -> None:
    assets = config.universe.enabled_assets()
    assert len(assets) == 18
    groups = {a.group for a in assets.values()}
    assert groups == {"Aktien", "Anleihen", "Sachwerte", "Diversifikatoren", "Liquidität"}
    assert config.currency.base == "EUR"
    assert config.currency.supported == ["EUR", "USD", "CHF", "GBP"]


def test_bonds_hedged_equities_and_real_assets_unhedged(config: AppConfig) -> None:
    for key, asset in config.universe.assets.items():
        if asset.group == "Anleihen":
            assert asset.hedged, key
        if asset.group in ("Aktien", "Sachwerte", "Diversifikatoren"):
            assert not asset.hedged, key


def test_bitcoin_special_rules(config: AppConfig) -> None:
    bitcoin = config.universe.assets["bitcoin"]
    assert bitcoin.max_weight == 0.03
    assert bitcoin.in_regime_features is False
    assert config.base.constraints["max_weight"]["bitcoin"] == 0.03


def test_paid_sources_prepared_but_disabled(config: AppConfig) -> None:
    for name in ("eodhd", "sipa", "msci"):
        source = config.sources.sources[name]
        assert source.paid and not source.enabled and source.requires_key


def test_regime_map_covers_every_asset_and_quadrant(config: AppConfig) -> None:
    assert set(config.regime_map.expectations) == set(config.universe.assets)
    for vector in config.regime_map.expectations.values():
        assert set(vector) == set(QUADRANTS)
    assert config.regime_map.rules.logistic_k == 1.5


def test_config_hash_is_stable_and_sensitive(tmp_path: Path) -> None:
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    first = config_hash(tmp_path / "config")
    assert first == config_hash(tmp_path / "config") == load_config(tmp_path / "config").config_hash
    with (tmp_path / "config" / "currency.yaml").open("a", encoding="utf-8") as handle:
        handle.write("\n# Änderung\n")
    assert config_hash(tmp_path / "config") != first


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Segment(id="x", kind="price", quality="proxy", symbols={"yfinance": "X"}, tippfehler=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Segment(id="x", kind="synthetic_bond", quality="synthetisch")


def test_cli_help_and_version() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "data" in result.output and "config" in result.output
    assert "allocation-navigator" in runner.invoke(app, ["version"]).output


def test_cli_config_check() -> None:
    result = runner.invoke(app, ["config", "check", "--root", str(REPO_ROOT)])
    assert result.exit_code == 0, result.output
    assert "18 eingeschaltet" in result.output


def test_cli_later_milestones_exit_with_notice() -> None:
    result = runner.invoke(app, ["backtest"])
    assert result.exit_code == 2
    assert "noch nicht implementiert" in result.output


def test_cli_demo_update_and_validate(tmp_path: Path) -> None:
    shutil.copytree(REPO_ROOT / "config", tmp_path / "config")
    update = runner.invoke(app, ["data", "update", "--demo", "--root", str(tmp_path)])
    assert update.exit_code == 0, update.output
    assert "DEMO-DATEN" in update.output
    validate = runner.invoke(app, ["data", "validate", "--demo", "--root", str(tmp_path)])
    assert validate.exit_code == 0, validate.output
    assert "EUR: 18/18, USD: 18/18, CHF: 18/18, GBP: 18/18" in validate.output
    report = (tmp_path / "reports_demo" / "validation_latest.md").read_text(encoding="utf-8")
    assert "DEMO-DATEN" in report and "Universum in CHF" in report
    assert (tmp_path / "reports_demo" / "validation_latest.html").exists()
    assert not (tmp_path / "data").exists(), "Demo-Daten dürfen nie im echten Datenordner landen"
