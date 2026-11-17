"""Methode B: statistische Regime-Erkennung mit Hidden-Markov-Modell (Spezifikation 5.1).

Ablauf:

- Neuschätzung mit expandierendem Fenster einmal je Jahr (Monatsende ``refit_month``), mit
  mehreren Startwerten; das Modell mit der höchsten Log-Likelihood gewinnt.
- Zwischen zwei Neuschätzungen werden die Wahrscheinlichkeiten monatlich **gefiltert**: Für den
  Stichtag t zählen nur Beobachtungen bis t (Vorwärtsrekursion). Geglättete
  Wahrscheinlichkeiten und der Viterbi-Pfad nutzen künftige Daten und kommen hier nicht vor.
- Benennung: Die Zustände werden über ihre mittleren Wachstums- und Inflationswerte den
  Quadranten zugeordnet (Ungarische Methode). So bleiben die Namen über Neuschätzungen hinweg
  gleich. Passt ein Zustand zu keinem Quadranten und zeigt er hohen Stress (Volatilität,
  Kreditspread), heißt er „Finanzstress"; seine Wahrscheinlichkeit zählt im Vergleich mit
  Methode A zum zugeordneten Quadranten.
- Gegencheck: Mischverteilungsmodell (Gaussian Mixture) ohne Zeitdynamik mit denselben
  Merkmalen und demselben Neuschätzungsplan.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.special import logsumexp

from navigator.config import QUADRANTS, HmmConfig

log = logging.getLogger(__name__)
logging.getLogger("hmmlearn").setLevel(logging.ERROR)  # Konvergenzmeldungen je Start

CENTERS = {
    "disinflationary_boom": (1.0, -1.0),
    "reflation": (1.0, 1.0),
    "deflationary_bust": (-1.0, -1.0),
    "stagflation": (-1.0, 1.0),
}
STRESS_FEATURES = ("equity_vol_3m", "credit_spread_level")


@dataclass
class GaussianParams:
    """Parameter eines gaußschen Modells mit diagonaler Kovarianz."""

    means: np.ndarray  # (k, d)
    variances: np.ndarray  # (k, d)
    weights: np.ndarray  # (k,) Startverteilung bzw. Mischgewichte
    transmat: np.ndarray | None = None  # (k, k) nur HMM
    loglik: float = float("nan")

    def log_densities(self, x: np.ndarray) -> np.ndarray:
        """log N(x | μ_s, diag σ²_s) je Beobachtung und Zustand: (n, k)."""
        diff = x[:, None, :] - self.means[None, :, :]
        return -0.5 * (
            np.log(2.0 * np.pi * self.variances)[None, :, :] + diff**2 / self.variances[None, :, :]
        ).sum(axis=2)

    def feature_loglik(self, x: np.ndarray, state: int) -> np.ndarray:
        """Beitrag jedes Merkmals zur Log-Dichte eines Zustands (diagonal: summierbar)."""
        var = self.variances[state]
        return -0.5 * (np.log(2.0 * np.pi * var) + (x - self.means[state]) ** 2 / var)


def prepare(features: pd.DataFrame, min_share: float) -> pd.DataFrame:
    """Zeilen mit genügend Merkmalen; fehlende Werte = 0 (Durchschnitt der z-Werte)."""
    share = features.notna().mean(axis=1)
    usable = features[share >= min_share]
    return usable.fillna(0.0)


def forward_filter(x: np.ndarray, params: GaussianParams) -> np.ndarray:
    """Gefilterte Zustandswahrscheinlichkeiten P(s_t | x_1..x_t) je Zeitpunkt (n, k)."""
    assert params.transmat is not None
    log_b = params.log_densities(x)
    log_a = np.log(np.clip(params.transmat, 1e-300, None))
    n, k = log_b.shape
    out = np.empty((n, k))
    alpha = np.log(np.clip(params.weights, 1e-300, None)) + log_b[0]
    alpha -= logsumexp(alpha)
    out[0] = alpha
    for t in range(1, n):
        alpha = logsumexp(alpha[:, None] + log_a, axis=0) + log_b[t]
        alpha -= logsumexp(alpha)
        out[t] = alpha
    return np.exp(out)


def fit_hmm(
    x: np.ndarray, n_states: int, config: HmmConfig, seed_offset: int = 0
) -> GaussianParams:
    """Schätzt ein HMM mit mehreren Startwerten; das beste nach Log-Likelihood."""
    from hmmlearn.hmm import GaussianHMM

    best: GaussianParams | None = None
    for start in range(config.n_starts):
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=config.max_iter,
            tol=config.tol,
            random_state=config.seed + seed_offset * 101 + start,
            min_covar=1e-3,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                model.fit(x)
                loglik = float(model.score(x))
            except (ValueError, np.linalg.LinAlgError) as exc:
                log.debug("HMM-Start %d gescheitert: %s", start, exc)
                continue
        if not np.isfinite(loglik):
            continue
        params = GaussianParams(
            means=np.asarray(model.means_),
            variances=np.asarray([np.diag(c) for c in model.covars_]),
            weights=np.asarray(model.startprob_),
            transmat=np.asarray(model.transmat_),
            loglik=loglik,
        )
        if best is None or loglik > best.loglik:
            best = params
    if best is None:
        raise RuntimeError("HMM: keine Schätzung konvergierte")
    return best


def fit_gmm(
    x: np.ndarray, n_states: int, config: HmmConfig, seed_offset: int = 0
) -> GaussianParams:
    """Schätzt das Mischverteilungsmodell (Gegencheck ohne Zeitdynamik)."""
    from sklearn.mixture import GaussianMixture

    model = GaussianMixture(
        n_components=n_states,
        covariance_type="diag",
        n_init=config.n_starts,
        max_iter=config.max_iter,
        tol=config.tol,
        random_state=config.seed + seed_offset,
        reg_covar=1e-3,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(x)
    return GaussianParams(
        means=np.asarray(model.means_),
        variances=np.asarray(model.covariances_),
        weights=np.asarray(model.weights_),
        loglik=float(model.score(x) * len(x)),
    )


def gmm_probabilities(x: np.ndarray, params: GaussianParams) -> np.ndarray:
    """Zustandswahrscheinlichkeiten nur aus x_t (keine Zeitdynamik)."""
    log_p = params.log_densities(x) + np.log(np.clip(params.weights, 1e-300, None))[None, :]
    return np.exp(log_p - logsumexp(log_p, axis=1, keepdims=True))


def name_states(
    params: GaussianParams,
    columns: list[str],
    growth: list[str],
    inflation: list[str],
    stress_threshold: float,
) -> tuple[list[str], list[str]]:
    """Ordnet die Zustände Quadranten zu (Ungarische Methode).

    Liefert je Zustand den zugeordneten Quadranten und seinen Namen (Quadrant oder
    ``financial_stress``).
    """
    index = {c: i for i, c in enumerate(columns)}
    g_cols = [index[c] for c in growth if c in index]
    i_cols = [index[c] for c in inflation if c in index]
    s_cols = [index[c] for c in STRESS_FEATURES if c in index]
    points = np.column_stack(
        [
            params.means[:, g_cols].mean(axis=1) if g_cols else np.zeros(len(params.means)),
            params.means[:, i_cols].mean(axis=1) if i_cols else np.zeros(len(params.means)),
        ]
    )
    centers = np.array([CENTERS[q] for q in QUADRANTS])
    k = len(points)
    cost = ((points[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    assigned: list[str] = [""] * k
    if k <= len(QUADRANTS):
        rows, cols = linear_sum_assignment(cost)
        for r, c in zip(rows, cols, strict=True):
            assigned[r] = QUADRANTS[c]
    else:  # mehr Zustände als Quadranten: je Zustand der nächste Quadrant
        for r in range(k):
            assigned[r] = QUADRANTS[int(np.argmin(cost[r]))]
    names = []
    for r in range(k):
        g_sign, i_sign = CENTERS[assigned[r]]
        contradicts = (points[r, 0] * g_sign < -0.25) and (points[r, 1] * i_sign < -0.25)
        stress = float(params.means[r, s_cols].mean()) if s_cols else 0.0
        names.append(
            "financial_stress" if contradicts and stress > stress_threshold else assigned[r]
        )
    return assigned, names


def bic(params: GaussianParams, n: int, hmm: bool = True) -> float:
    """Bayes-Informationskriterium (kleiner ist besser)."""
    k, d = params.means.shape
    free = (k - 1) + 2 * k * d + (k * (k - 1) if hmm else 0)
    return float(-2.0 * params.loglik + free * np.log(n))


@dataclass
class MethodBResult:
    """Ergebnis von Methode B je Stichtag."""

    features: pd.DataFrame
    probs: pd.DataFrame  # Quadranten-Wahrscheinlichkeiten (gefiltert)
    state_probs: pd.DataFrame  # je Zustandsname, Spalten state_0..k
    regime: pd.Series  # Quadrant mit höchster Wahrscheinlichkeit
    label: pd.Series  # Zustandsname (Quadrant oder financial_stress)
    gmm_probs: pd.DataFrame
    gmm_regime: pd.Series
    models: dict[pd.Timestamp, GaussianParams] = field(default_factory=dict)
    model_of: pd.Series = field(default_factory=pd.Series)  # Stichtag -> Modellzeitpunkt
    names: dict[pd.Timestamp, list[str]] = field(default_factory=dict)
    assigned: dict[pd.Timestamp, list[str]] = field(default_factory=dict)
    bic_table: pd.DataFrame = field(default_factory=pd.DataFrame)

    def transition_matrix(self, when: pd.Timestamp | None = None) -> pd.DataFrame:
        """Übergangsmatrix des zum Stichtag gültigen Modells (Zeilen: von, Spalten: nach)."""
        key = self.model_of.dropna().iloc[-1] if when is None else self.model_of[when]
        params = self.models[key]
        labels = {
            "disinflationary_boom": "Aufschwung",
            "reflation": "Reflation",
            "deflationary_bust": "Rezession",
            "stagflation": "Stagflation",
            "financial_stress": "Finanzstress",
        }
        names = [f"{i}: {labels.get(n, n)}" for i, n in enumerate(self.names[key])]
        assert params.transmat is not None
        return pd.DataFrame(params.transmat, index=names, columns=names)

    def expected_duration(self, when: pd.Timestamp | None = None) -> pd.Series:
        """Erwartete Verweildauer je Zustand in Monaten: 1 / (1 − p_ii)."""
        matrix = self.transition_matrix(when)
        diag = np.clip(np.diag(matrix.to_numpy()), 0.0, 1.0 - 1e-9)
        return pd.Series(1.0 / (1.0 - diag), index=matrix.index)


def refit_dates(index: pd.DatetimeIndex, config: HmmConfig) -> list[pd.Timestamp]:
    """Neuschätzungstermine: jeweils das Monatsende von ``refit_month`` nach Mindesthistorie."""
    if len(index) <= config.min_train_months:
        return []
    first = index[config.min_train_months - 1]
    dates = [d for d in index if d >= first and d.month == config.refit_month]
    if not dates or dates[0] != first:
        dates.insert(0, first)
    return dates


def run_method_b(
    features: pd.DataFrame,
    config: HmmConfig,
    growth: list[str],
    inflation: list[str],
) -> MethodBResult:
    """Methode B über alle Stichtage mit expandierendem Fenster (nur Daten bis t)."""
    data = prepare(features, config.min_feature_share)
    columns = list(data.columns)
    empty = pd.DataFrame(np.nan, index=features.index, columns=list(QUADRANTS))
    probs, gmm_probs = empty.copy(), empty.copy()
    state_probs = pd.DataFrame(
        np.nan, index=features.index, columns=[f"state_{i}" for i in range(config.n_states)]
    )
    label = pd.Series(None, index=features.index, dtype="object")
    model_of = pd.Series(pd.NaT, index=features.index, dtype="datetime64[ns]")
    result = MethodBResult(
        features=data,
        probs=probs,
        state_probs=state_probs,
        regime=pd.Series(None, index=features.index, dtype="object"),
        label=label,
        gmm_probs=gmm_probs,
        gmm_regime=pd.Series(None, index=features.index, dtype="object"),
        model_of=model_of,
    )
    refits = refit_dates(pd.DatetimeIndex(data.index), config)
    for number, fit_date in enumerate(refits):
        train = data.loc[:fit_date].to_numpy()
        hmm = fit_hmm(train, config.n_states, config, number)
        gmm = fit_gmm(train, config.n_states, config, number)
        assigned, names = name_states(hmm, columns, growth, inflation, config.stress_threshold)
        gmm_assigned, _ = name_states(gmm, columns, growth, inflation, config.stress_threshold)
        result.models[fit_date] = hmm
        result.names[fit_date] = names
        result.assigned[fit_date] = assigned
        until = refits[number + 1] if number + 1 < len(refits) else None
        window = data.index[(data.index >= fit_date) & ((data.index < until) if until else True)]
        upto = data.loc[: window[-1]].to_numpy()
        filtered = forward_filter(upto, hmm)[-len(window) :]
        mixture = gmm_probabilities(data.loc[window].to_numpy(), gmm)
        for row, when in enumerate(window):
            state_probs.loc[when] = filtered[row]
            for state, quadrant in enumerate(assigned):
                probs.loc[when, quadrant] = np.nansum(
                    [probs.loc[when, quadrant], filtered[row, state]]
                )
            for state, quadrant in enumerate(gmm_assigned):
                gmm_probs.loc[when, quadrant] = np.nansum(
                    [gmm_probs.loc[when, quadrant], mixture[row, state]]
                )
            label[when] = names[int(np.argmax(filtered[row]))]
            model_of[when] = fit_date
    complete = probs.notna().any(axis=1)
    probs.loc[complete] = probs.loc[complete].fillna(0.0)
    gmm_probs.loc[complete] = gmm_probs.loc[complete].fillna(0.0)
    result.regime[complete] = probs.loc[complete].idxmax(axis=1)
    result.gmm_regime[complete] = gmm_probs.loc[complete].idxmax(axis=1)
    if len(data) > config.min_train_months:
        rows = []
        full = data.to_numpy()
        for k in config.bic_states:
            try:
                params = fit_hmm(full, k, config, 999)
            except RuntimeError:
                continue
            rows.append(
                {"Zustände": k, "Log-Likelihood": params.loglik, "BIC": bic(params, len(full))}
            )
        result.bic_table = pd.DataFrame(rows)
    return result
