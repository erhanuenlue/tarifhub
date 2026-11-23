"""Exact power of the paired sign test planned for the Phase 4 embedding comparison.

The Phase 4 feasibility page (docs/evidence/2026-11-22-phase4-finetuning-feasibility.md) makes a
paired hit at 5 per held-out unit the primary endpoint and tests it with an exact sign test. This
module computes, without approximation, how likely that test is to find a difference in the
tuned model's favour:

- n independent units (held-out questions, or families where questions share evidence);
- each unit is a win (the tuned model hits at 5, the base model misses) with probability w, a
  loss (the tuned model misses, the base model hits) with probability l, or a tie with
  probability t = 1 - w - l;
- the test drops the ties; with d discordant units of which k are wins and X ~ Binomial(d, 1/2),
  the two-sided p-value is min(1, 2 * min(P(X <= k), P(X >= k))) and the one-sided p-value, in
  the tuned model's favour, is P(X >= k); the test rejects when p <= alpha;
- power counts only rejections in the tuned model's favour (k > d - k): it sums, over the (d, k)
  where the test rejects, the multinomial probability of k wins, d - k losses and n - d ties.

p-values are dyadic rationals, computed as fractions and compared with alpha exactly; a float
alpha is read as the decimal it prints as (0.05 is 1/20). Probabilities and power are floats.
Exact power is saw-toothed in n, so n_for_power reports both the first n that reaches a target
and the n from which the target holds for every larger n up to n_max.

Standard library only, no network, nothing read from disk. The CLI writes a deterministic JSON
report (sorted keys, floats rounded to 4 decimal places, no timestamps, no paths):

    python3 tools/commentary_rag/sign_test_power.py --out <a new file>

An existing file is never replaced.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from fractions import Fraction

# Up to 400 units a binomial term is computed as comb * s**j * f**(m - j) without overflow, and a
# factor that underflows can only lose terms below about 1e-189, which no power figure can notice;
# the planned comparisons need well under a hundred units.
MAX_UNITS = 400

ALPHA = 0.05
TARGET = 0.8
N_MAX = 400
STEP = 0.01
SIDES = {"two_sided": 2, "one_sided": 1}
SCENARIOS = {  # per-unit win and loss probabilities (w, l)
    "S1": (0.20, 0.00),
    "S2": (0.30, 0.10),
    "S3": (0.10, 0.00),
    "S4": (0.30, 0.00),
    "S5": (0.20, 0.05),
    "S6": (0.40, 0.10),
    "S7": (1 / 6, 0.00),  # base miss rate on dev cases D1 to D6 (5 of 6 hit), every miss fixed
}
SCENARIO_N = (6, 10, 20, 30, 38, 40, 50, 60)
FAMILY_W = (0.5, 0.67, 0.8, 0.9, 1.0)
FAMILY_N = (4, 5, 6, 9, 11)
FAMILY_D = tuple(range(1, 13))
MIN_W_N = (30, 38, 40)
LOSS_RATIOS = {"0": 0.0, "1/3": 1 / 3}

MODEL_TEXT = (
    "n independent units (held-out questions, or families). Each unit is a win (the tuned model"
    " hits at 5, the base model misses) with probability w, a loss (the tuned model misses, the"
    " base model hits) with probability l, or a tie with probability t = 1 - w - l. The exact"
    " sign test drops the ties; with d discordant units of which k are wins and"
    " X ~ Binomial(d, 1/2), the two-sided p-value is min(1, 2 * min(P(X <= k), P(X >= k))) and"
    " the one-sided p-value is P(X >= k), both exact fractions, and the test rejects when"
    " p <= alpha. Power is the exact multinomial probability of a rejection in the tuned"
    " model's favour (k > d - k)."
)
NOTES = {
    "family_units": "units are families, a family's sign being that of its summed per-question"
    " differences in hit at 5 (ties dropped); w_f is the family-level win probability, l_f = 0",
    "min_w_at_n": "the smallest w on the grid 0.01, 0.02, ... (l = loss_ratio * w, w + l <= 1)"
    " whose power at n reaches target_power; null if none does",
    "n_for_power": "first_n: the smallest n whose power reaches target_power; stable_n: the"
    " smallest n from which the power stays at or above it for every n up to n_max; null when"
    " not reached. Exact power is saw-toothed in n, so the two can differ",
}


def _count(value: object, name: str) -> int:
    """value as a non-negative int (bools refused), or ValueError."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    return value


def _units(value: object, name: str = "n") -> int:
    count = _count(value, name)
    if count > MAX_UNITS:
        raise ValueError(f"{name} must be at most {MAX_UNITS}, got {count}")
    return count


def _sides(sides: object) -> int:
    if isinstance(sides, bool) or not isinstance(sides, int) or sides not in (1, 2):
        raise ValueError(f"sides must be 1 or 2, got {sides!r}")
    return sides


def _real(value: object, name: str) -> float:
    """value (int, float or Fraction; bools refused) as a finite float, or ValueError."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise ValueError(f"{name} must be a real number, got {value!r}")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{name} is out of range, got {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return number


def _exact(value: int | float | Fraction) -> Fraction:
    """A float read as the decimal it prints as (0.05 is 1/20), anything else exactly."""
    return Fraction(repr(value)) if isinstance(value, float) else Fraction(value)


def _alpha(alpha: object) -> Fraction:
    """alpha as an exact fraction strictly between 0 and 1, or ValueError."""
    _real(alpha, "alpha")
    exact = _exact(alpha)
    if not 0 < exact < 1:
        raise ValueError(f"alpha must lie strictly between 0 and 1, got {alpha!r}")
    return exact


def _probabilities(win: object, loss: object) -> tuple[float, float]:
    """(w, l) as floats once 0 <= w, 0 <= l and w + l <= 1 hold, or ValueError."""
    w_value, l_value = _real(win, "w"), _real(loss, "l")
    if w_value < 0 or l_value < 0 or w_value + l_value > 1:
        raise ValueError(f"need 0 <= w, 0 <= l and w + l <= 1, got w={win!r}, l={loss!r}")
    return w_value, l_value


def _target(target: object) -> float:
    value = _real(target, "target")
    if not 0 < value <= 1:
        raise ValueError(f"target must lie in (0, 1], got {target!r}")
    return value


def sign_test_p(k: int, d: int, sides: int = 2) -> Fraction:
    """Exact p-value of the sign test for k wins among d discordant units (ties dropped).

    With X ~ Binomial(d, 1/2): two-sided min(1, 2 * min(P(X <= k), P(X >= k))), one-sided
    P(X >= k), the side that favours the tuned model.
    """
    d, k, sides = _count(d, "d"), _count(k, "k"), _sides(sides)
    if k > d:
        raise ValueError(f"k must not exceed d, got k={k}, d={d}")
    at_least = sum(math.comb(d, j) for j in range(k, d + 1))  # 2**d * P(X >= k)
    if sides == 1:
        return Fraction(at_least, 2**d)
    at_most = sum(math.comb(d, j) for j in range(k + 1))  # 2**d * P(X <= k)
    return min(Fraction(1), Fraction(2 * min(at_most, at_least), 2**d))


def min_wins_to_reject(d: int, alpha: float | Fraction = ALPHA, sides: int = 2) -> int | None:
    """Smallest k with k > d - k at which the test rejects among d discordant units, else None.

    For k > d - k the p-value is min(1, sides * P(X >= k)), which falls as k grows, so the test
    rejects at every k from the returned value up to d.
    """
    return _min_wins(_count(d, "d"), _alpha(alpha), _sides(sides))


def _min_wins(d: int, alpha: Fraction, sides: int) -> int | None:
    smallest = None
    at_least = 0  # 2**d * P(X >= k) while k walks down from d
    for k in range(d, d // 2, -1):  # exactly the k with k > d - k
        at_least += math.comb(d, k)
        if Fraction(sides * at_least, 2**d) > alpha:
            break
        smallest = k
    return smallest


def _term(m: int, j: int, success: float, failure: float) -> float:
    """comb(m, j) * success**j * failure**(m - j), with 0**0 = 1: one binomial probability."""
    return math.comb(m, j) * success**j * failure ** (m - j)


def _shares(win: float, loss: float) -> tuple[float, float]:
    """A discordant unit's chance of being a win or a loss, w / (w + l) and l / (w + l)."""
    discordant = win + loss
    if discordant == 0:
        return 0.0, 0.0
    return win / discordant, loss / discordant


def outcome_mass(n: int, d: int, k: int, w: float, l: float) -> float:  # noqa: E741
    """Probability of exactly k wins, d - k losses and n - d ties among n units.

    The multinomial term n!/(k!(d-k)!(n-d)!) * w**k * l**(d-k) * t**(n-d), evaluated as
    P(D = d) * P(K = k | D = d), D the discordant count and K its wins, so that no intermediate
    value leaves the float range.
    """
    n, d, k = _units(n), _count(d, "d"), _count(k, "k")
    if d > n or k > d:
        raise ValueError(f"need k <= d <= n, got k={k}, d={d}, n={n}")
    win, loss = _probabilities(w, l)
    p, r = _shares(win, loss)
    return _term(n, d, win + loss, 1.0 - (win + loss)) * _term(d, k, p, r)


def power(
    n: int, w: float, l: float, alpha: float | Fraction = ALPHA, sides: int = 2,  # noqa: E741
) -> float:
    """Exact probability that the test rejects in the tuned model's favour among n units.

    The sum of outcome_mass over every (d, k) with k > d - k and p <= alpha, grouped by d: the
    chance of d discordant units times the chance that their wins reach min_wins_to_reject(d).
    """
    n = _units(n)
    win, loss = _probabilities(w, l)
    tails = _tails(win, loss, _thresholds(n, _alpha(alpha), _sides(sides)))
    return _power_from_tails(n, win, loss, tails)


def _thresholds(d_max: int, alpha: Fraction, sides: int) -> list[int | None]:
    """min_wins_to_reject(d) for d = 0..d_max."""
    return [_min_wins(d, alpha, sides) for d in range(d_max + 1)]


def _tails(win: float, loss: float, thresholds: list[int | None]) -> list[float]:
    """For each d, the chance that d discordant units hold enough wins for a rejection."""
    p, r = _shares(win, loss)
    return [0.0 if k_min is None else math.fsum(_term(d, k, p, r) for k in range(k_min, d + 1))
            for d, k_min in enumerate(thresholds)]


def _power_from_tails(n: int, win: float, loss: float, tails: list[float]) -> float:
    """Power for n units: the sum over d of P(D = d) times the rejection tail at d."""
    discordant = win + loss
    return math.fsum(_term(n, d, discordant, 1.0 - discordant) * tails[d]
                     for d in range(n + 1) if tails[d])


def n_for_power(  # noqa: PLR0913
    w: float,
    l: float,  # noqa: E741
    target: float = TARGET,
    alpha: float | Fraction = ALPHA,
    sides: int = 2,
    n_max: int = N_MAX,
) -> dict[str, int | None]:
    """The unit counts at which power reaches target, scanning n = 0..n_max.

    first_n is the smallest n whose power reaches target; stable_n the smallest n from which
    the power stays at or above target for every n up to n_max. Each is None if not reached.
    """
    win, loss = _probabilities(w, l)
    goal = _target(target)
    n_max = _units(n_max, "n_max")
    tails = _tails(win, loss, _thresholds(n_max, _alpha(alpha), _sides(sides)))
    reached = [_power_from_tails(n, win, loss, tails) >= goal for n in range(n_max + 1)]
    first_n = next((n for n, ok in enumerate(reached) if ok), None)
    stable_n = None
    for n in range(n_max, -1, -1):
        if not reached[n]:
            break
        stable_n = n
    return {"first_n": first_n, "stable_n": stable_n}


def min_w_for_power(  # noqa: PLR0913
    n: int,
    loss_ratio: float,
    target: float = TARGET,
    alpha: float | Fraction = ALPHA,
    sides: int = 2,
    step: float = STEP,
) -> float | None:
    """The smallest w on the grid step, 2 * step, ... whose power at n reaches target, else None.

    Each grid point sets l = loss_ratio * w; the grid ends where w + l would exceed 1. The test
    is discrete, so power need not rise steadily with w: this is the first grid point that
    reaches the target, not a bound above which every w does.
    """
    n = _units(n)
    ratio = _real(loss_ratio, "loss_ratio")
    if ratio < 0:
        raise ValueError(f"loss_ratio must not be negative, got {loss_ratio!r}")
    goal = _target(target)
    _real(step, "step")
    grid_step = _exact(step)
    if not 0 < grid_step <= 1:
        raise ValueError(f"step must lie in (0, 1], got {step!r}")
    thresholds = _thresholds(n, _alpha(alpha), _sides(sides))
    for i in range(1, math.floor(1 / grid_step) + 1):
        win = float(i * grid_step)
        loss = ratio * win
        if win + loss > 1:
            break
        if _power_from_tails(n, win, loss, _tails(win, loss, thresholds)) >= goal:
            return win
    return None


def _rounded(value: object) -> object:
    """value with every float rounded to 4 decimal places, through dicts and lists."""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def build_report() -> dict:
    """The report the CLI writes: the scenarios, the family-level view and the minimum w."""
    scenarios = {
        name: {
            "w": win,
            "l": loss,
            "t": 1.0 - (win + loss),
            "power": [
                {"n": n, **{side: power(n, win, loss, ALPHA, s) for side, s in SIDES.items()}}
                for n in SCENARIO_N
            ],
            "n_for_power": {
                side: n_for_power(win, loss, TARGET, ALPHA, s, N_MAX) for side, s in SIDES.items()
            },
        }
        for name, (win, loss) in SCENARIOS.items()
    }
    family_units = {
        "l_f": 0.0,
        "sides": 2,
        "power": [
            {"w_f": w_f, "n": n, "power": power(n, w_f, 0.0, ALPHA, 2)}
            for w_f in FAMILY_W for n in FAMILY_N
        ],
        "min_wins_to_reject": [
            {"d": d, **{side: min_wins_to_reject(d, ALPHA, s) for side, s in SIDES.items()}}
            for d in FAMILY_D
        ],
    }
    min_w_at_n = [
        {"loss_ratio": label, "n": n,
         **{side: min_w_for_power(n, ratio, TARGET, ALPHA, s, STEP) for side, s in SIDES.items()}}
        for label, ratio in LOSS_RATIOS.items() for n in MIN_W_N
    ]
    model = {
        "description": MODEL_TEXT,
        "alpha": ALPHA,
        "target_power": TARGET,
        "n_max": N_MAX,
        "w_grid_step": STEP,
        "rounding": "floats rounded to 4 decimal places",
        "notes": NOTES,
    }
    return _rounded({"model": model, "scenarios": scenarios, "family_units": family_units,
                     "min_w_at_n": min_w_at_n})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the exact sign-test power report for the Phase 4 comparison (JSON).")
    parser.add_argument("--out", required=True, help="path of the JSON report to write")
    args = parser.parse_args(argv)
    if os.path.exists(args.out):  # recorded reports are evidence, never replaced
        print(f"refused: {args.out} already exists; write a new report instead", file=sys.stderr)
        return 1
    text = json.dumps(build_report(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    with open(args.out, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
