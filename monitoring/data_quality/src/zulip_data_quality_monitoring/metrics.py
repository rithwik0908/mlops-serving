from __future__ import annotations

from collections import Counter
from math import log
from typing import Iterable

import pandas as pd


ALLOWED_LABELS = {-1, 0, 1}


def ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def null_rate(series: pd.Series) -> float:
    return ratio(float(series.isna().sum()), float(len(series)))


def duplicate_rate(series: pd.Series) -> float:
    if len(series) == 0:
        return 0.0
    return ratio(float(series.duplicated().sum()), float(len(series)))


def invalid_label_rate(series: pd.Series) -> float:
    if len(series) == 0:
        return 0.0
    valid_mask = series.isna() | series.isin(ALLOWED_LABELS)
    return ratio(float((~valid_mask).sum()), float(len(series)))


def class_distribution(series: pd.Series) -> dict[str, float]:
    counts = series.dropna().astype(int).value_counts().to_dict()
    total = sum(counts.values())
    return {str(label): ratio(count, total) for label, count in sorted(counts.items())}


def entropy(values: Iterable[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return round(-sum((count / total) * log(count / total, 2) for count in counts.values()), 4)


def word_count_stats(series: pd.Series) -> dict[str, float]:
    counts = series.fillna("").astype(str).str.split().str.len()
    if counts.empty:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "mean": round(float(counts.mean()), 2),
        "p50": round(float(counts.quantile(0.5)), 2),
        "p95": round(float(counts.quantile(0.95)), 2),
    }


def char_count_stats(series: pd.Series) -> dict[str, float]:
    counts = series.fillna("").astype(str).str.len()
    if counts.empty:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "mean": round(float(counts.mean()), 2),
        "p50": round(float(counts.quantile(0.5)), 2),
        "p95": round(float(counts.quantile(0.95)), 2),
    }


def estimated_formality(series: pd.Series) -> pd.Series:
    lowered = series.fillna("").astype(str).str.lower()
    polite = lowered.str.count(r"\bplease\b|\bthank\b|\bcould you\b|\bwould you\b|\bi appreciate\b|\bkindly\b")
    informal = lowered.str.count(r"\bhey\b|\byo\b|\bu\b|\bgonna\b|\bwanna\b|\bbtw\b|\bomg\b|\blol\b")
    words = lowered.str.split().str.len().clip(lower=1)
    return (polite - informal) / words


def psi(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    if reference.empty or current.empty:
        return 0.0
    ref = pd.to_numeric(reference, errors="coerce").dropna()
    cur = pd.to_numeric(current, errors="coerce").dropna()
    if ref.empty or cur.empty:
        return 0.0
    edges = sorted(ref.quantile([i / bins for i in range(bins + 1)]).unique())
    if len(edges) < 2:
        return 0.0
    ref_bins = pd.cut(ref, bins=edges, include_lowest=True, duplicates="drop").value_counts(normalize=True)
    cur_bins = pd.cut(cur, bins=edges, include_lowest=True, duplicates="drop").value_counts(normalize=True)
    joined = pd.concat([ref_bins, cur_bins], axis=1).fillna(1e-6)
    joined.columns = ["ref", "cur"]
    score = ((joined["cur"] - joined["ref"]) * (joined["cur"] / joined["ref"]).map(log)).sum()
    return round(float(score), 4)
