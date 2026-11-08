"""Statistics written out by hand, so every number in the report can be explained.

No scipy or sklearn: Wilson intervals, Cohen's kappa, precision / recall and a
scenario-clustered bootstrap are short enough to read in full.
"""

import math
import random
from collections import Counter, defaultdict

Z95 = 1.959964


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float, float]:
    """Proportion with Wilson score interval: (p, low, high). Better than the
    normal approximation for small n and proportions near 0 or 1."""
    if n == 0:
        return (float("nan"),) * 3
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def cohens_kappa(a: list, b: list) -> float:
    """Agreement between two raters beyond chance: (p_o - p_e) / (1 - p_e)."""
    if len(a) != len(b) or not a:
        raise ValueError("need two label lists of equal, non-zero length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def confusion(gold: list, pred: list) -> dict:
    """{gold_label: {predicted_label: count}}."""
    table = defaultdict(Counter)
    for g, p in zip(gold, pred):
        table[g][p] += 1
    return {g: dict(c) for g, c in table.items()}


def binary_scores(gold: list, pred: list, positive) -> dict:
    """Precision, recall and false positive rate for one label value, one-vs-rest."""
    tp = sum(g == positive and p == positive for g, p in zip(gold, pred))
    fp = sum(g != positive and p == positive for g, p in zip(gold, pred))
    fn = sum(g == positive and p != positive for g, p in zip(gold, pred))
    tn = sum(g != positive and p != positive for g, p in zip(gold, pred))

    def ratio(x, y):
        return x / y if y else float("nan")

    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn), "fpr": ratio(fp, fp + tn)}


def cluster_bootstrap(rows: list[dict], value, cluster: str = "scenario_id",
                      n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Mean of value(row) with a 95 % interval from resampling whole scenarios.

    Repetitions of one scenario are not independent (same text, same model),
    so the interval resamples scenarios with all their repetitions, not rows.
    """
    groups = defaultdict(list)
    for r in rows:
        groups[r[cluster]].append(value(r))
    keys = list(groups)
    if not keys:
        return (float("nan"),) * 3
    rng = random.Random(seed)
    point = sum(v for k in keys for v in groups[k]) / sum(len(groups[k]) for k in keys)
    means = []
    for _ in range(n_boot):
        sample = [rng.choice(keys) for _ in keys]
        vals = [v for k in sample for v in groups[k]]
        means.append(sum(vals) / len(vals))
    means.sort()
    return point, means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def cluster_bootstrap_diff(rows_a: list[dict], rows_b: list[dict], value, cluster: str = "scenario_id",
                           n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Difference of means (a - b) with a scenario-clustered 95 % interval.
    The two groups are resampled independently (they are usually different
    scenarios, e.g. tv_bleed vs. clean)."""
    def grouped(rows):
        g = defaultdict(list)
        for r in rows:
            g[r[cluster]].append(value(r))
        return g
    ga, gb = grouped(rows_a), grouped(rows_b)
    if not ga or not gb:
        return (float("nan"),) * 3
    rng = random.Random(seed)

    def mean(groups, keys):
        vals = [v for k in keys for v in groups[k]]
        return sum(vals) / len(vals)
    ka, kb = list(ga), list(gb)
    point = mean(ga, ka) - mean(gb, kb)
    diffs = sorted(mean(ga, [rng.choice(ka) for _ in ka]) - mean(gb, [rng.choice(kb) for _ in kb])
                   for _ in range(n_boot))
    return point, diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot) - 1]
