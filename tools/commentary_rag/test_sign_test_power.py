"""Offline tests for the exact power of the paired sign test (Phase 4 embedding comparison).

Pure arithmetic: no model, no network and no file outside pytest's tmp_path. Expected values
are either worked by hand (noted at the test) or taken from exact_power below, which writes the
definition out as a double sum in fractions and shares no code with the module.

    uv run --project services/ingestion --frozen --offline --extra ai --extra dev \\
        python -m pytest tools/commentary_rag/test_sign_test_power.py -q
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sign_test_power as pst

SCRIPT = Path(__file__).resolve().parent / "sign_test_power.py"
ALPHA = Fraction(1, 20)


def exact_p(k: int, d: int, sides: int) -> Fraction:
    """The sign test's p-value for k wins among d discordant units, from its definition."""
    at_most = sum(Fraction(math.comb(d, j), 2**d) for j in range(k + 1))
    at_least = sum(Fraction(math.comb(d, j), 2**d) for j in range(k, d + 1))
    return at_least if sides == 1 else min(Fraction(1), 2 * min(at_most, at_least))


def exact_power(n: int, w: Fraction, loss: Fraction, sides: int) -> Fraction:
    """Power as the double sum over (d, k) of multinomial probabilities, in exact fractions."""
    tie = 1 - w - loss
    total = Fraction(0)
    for d in range(n + 1):
        for k in range(d + 1):
            if k > d - k and exact_p(k, d, sides) <= ALPHA:
                ways = math.factorial(n) // (
                    math.factorial(k) * math.factorial(d - k) * math.factorial(n - d))
                total += ways * w**k * loss ** (d - k) * tie ** (n - d)
    return total


def test_feasibility_page_controls():
    """The two figures the merged feasibility page quotes for 30 independent questions."""
    assert round(pst.power(30, 0.20, 0.00), 2) == 0.57
    assert round(pst.power(30, 0.30, 0.10), 2) == 0.31


def test_six_straight_wins_are_the_smallest_two_sided_rejection():
    assert pst.sign_test_p(6, 6) == Fraction(1, 32)
    assert pst.sign_test_p(6, 6) <= ALPHA
    assert pst.sign_test_p(5, 5) == Fraction(1, 16)
    assert pst.sign_test_p(5, 5) > ALPHA
    assert pst.min_wins_to_reject(5) is None
    assert pst.min_wins_to_reject(6) == 6
    # One-sided, five wins of five already give p = 1/32; four of four give 1/16.
    assert pst.min_wins_to_reject(5, sides=1) == 5
    assert pst.min_wins_to_reject(4, sides=1) is None


def test_p_values_are_exact_fractions_from_the_definition():
    for d in range(15):
        for k in range(d + 1):
            for sides in (1, 2):
                p = pst.sign_test_p(k, d, sides)
                assert isinstance(p, Fraction)
                assert p == exact_p(k, d, sides)
    assert pst.sign_test_p(0, 0) == 1


def test_min_wins_is_where_the_rejection_region_starts():
    """For k > d - k the test rejects at every k from min_wins_to_reject(d) to d, and only there."""
    for sides in (1, 2):
        for d in range(41):
            region = [k for k in range(d + 1)
                      if k > d - k and pst.sign_test_p(k, d, sides) <= ALPHA]
            start = pst.min_wins_to_reject(d, sides=sides)
            assert region == ([] if start is None else list(range(start, d + 1)))


def test_alpha_is_compared_exactly():
    """p = 1/32 rejects at alpha 1/32 but not a hair below it, which a float could not tell."""
    assert pst.min_wins_to_reject(6, alpha=Fraction(1, 32)) == 6
    assert pst.min_wins_to_reject(6, alpha=Fraction(1, 32) - Fraction(1, 10**30)) is None
    assert pst.min_wins_to_reject(6, alpha=0.03125) == 6  # 1/32 is exact in binary as well
    assert pst.power(30, 0.3, 0.1, alpha=0.05) == pst.power(30, 0.3, 0.1, alpha=Fraction(1, 20))


def test_power_is_zero_without_wins_and_needs_six_units():
    for n in (0, 1, 6, 30):
        for loss in (0.0, 0.1, 0.5, 1.0):
            for sides in (1, 2):
                assert pst.power(n, 0.0, loss, sides=sides) == 0.0
    assert pst.power(5, 1.0, 0.0) == 0.0  # p = 1/16 at best: five units never reach 5 %
    assert pst.power(6, 1.0, 0.0) == 1.0


@pytest.mark.parametrize(("n", "w", "loss"), [
    (0, 0.2, 0.1), (1, 0.5, 0.5), (7, 0.3, 0.1), (12, 0.0, 0.0), (9, 0.0, 1.0),
    (30, 0.2, 0.0), (40, 0.25, 0.05), (60, 0.4, 0.1),
])
def test_outcome_masses_sum_to_one(n, w, loss):
    masses = [pst.outcome_mass(n, d, k, w, loss) for d in range(n + 1) for k in range(d + 1)]
    assert min(masses) >= 0
    assert abs(math.fsum(masses) - 1) <= 1e-12


def test_outcome_mass_is_the_multinomial_term():
    n, w, loss = 11, 0.3, 0.1
    tie = 1 - w - loss
    for d in range(n + 1):
        for k in range(d + 1):
            ways = math.factorial(n) // (
                math.factorial(k) * math.factorial(d - k) * math.factorial(n - d))
            literal = ways * w**k * loss ** (d - k) * tie ** (n - d)
            assert pst.outcome_mass(n, d, k, w, loss) == pytest.approx(literal, rel=1e-12)


@pytest.mark.parametrize(("n", "w", "loss"), [
    (6, "0.5", "0.1"), (11, "0.3", "0.1"), (30, "0.2", "0"), (30, "0.3", "0.1"),
    (25, "0.4", "0.2"),
])
@pytest.mark.parametrize("sides", [1, 2])
def test_power_matches_the_exact_multinomial_sum(n, w, loss, sides):
    expected = float(exact_power(n, Fraction(w), Fraction(loss), sides))
    assert pst.power(n, float(w), float(loss), sides=sides) == pytest.approx(expected, abs=1e-12)
    region = math.fsum(
        pst.outcome_mass(n, d, k, float(w), float(loss))
        for d in range(n + 1) for k in range(d + 1)
        if k > d - k and pst.sign_test_p(k, d, sides) <= ALPHA)
    assert region == pytest.approx(expected, abs=1e-12)


def test_one_sided_power_is_never_below_two_sided():
    for n in (0, 5, 6, 10, 20, 38):
        for w, loss in ((0.2, 0.0), (0.3, 0.1), (0.1, 0.0), (0.4, 0.1), (0.5, 0.5), (1.0, 0.0)):
            assert pst.power(n, w, loss, sides=1) >= pst.power(n, w, loss, sides=2)
    assert pst.power(5, 1.0, 0.0, sides=1) == 1.0 > pst.power(5, 1.0, 0.0)


def test_n_for_power_on_a_hand_checked_saw_tooth():
    """No ties and w = 0.75, so the power at n is P(Bin(n, 0.75) >= min_wins_to_reject(n)).

    Worked by hand: the threshold is 8 of 9, 9 of 10, 10 of 11 and 10 of 12, giving 0.300, 0.244,
    0.197 and 0.391; from 12 to 20 the lowest value is 0.281 at n = 14. A target of 0.25 is first
    met at n = 9 but holds for good only from n = 12.
    """
    result = pst.n_for_power(0.75, 0.25, target=0.25, n_max=20)
    assert result == {"first_n": 9, "stable_n": 12}
    assert result["stable_n"] >= result["first_n"]
    assert pst.power(9, 0.75, 0.25) >= 0.25 > pst.power(11, 0.75, 0.25)
    assert all(pst.power(n, 0.75, 0.25) >= 0.25 for n in range(12, 21))
    # With n_max 10 the target is met at 9 and lost again at 10, so it never holds for good.
    assert pst.n_for_power(0.75, 0.25, target=0.25, n_max=10) == {"first_n": 9, "stable_n": None}


def test_n_for_power_simple_cases():
    assert pst.n_for_power(1.0, 0.0, n_max=10) == {"first_n": 6, "stable_n": 6}
    assert pst.n_for_power(0.2, 0.0, n_max=10) == {"first_n": None, "stable_n": None}
    assert pst.n_for_power(0.0, 0.3) == {"first_n": None, "stable_n": None}


def test_min_w_for_power_hand_checked():
    """Without losses, six units reject two-sided only when all six win, so power = w**6:
    0.96**6 = 0.783 < 0.8 <= 0.97**6 = 0.833. One-sided, five wins of five suffice (p = 1/32):
    0.95**5 = 0.774 < 0.8 <= 0.96**5 = 0.815.
    """
    assert pst.min_w_for_power(6, 0) == 0.97
    assert pst.min_w_for_power(5, 0) is None
    assert pst.min_w_for_power(5, 0, sides=1) == 0.96
    assert pst.min_w_for_power(6, 1) is None  # w = l = 0.5 at most, power 1/64
    third = 1 / 3
    w = pst.min_w_for_power(30, third)
    grid = [i / 100 for i in range(1, round(w * 100) + 1)]
    assert grid[-1] == w
    assert pst.power(30, w, third * w) >= 0.8
    assert all(pst.power(30, g, third * g) < 0.8 for g in grid[:-1])


INVALID = {
    "negative n": lambda: pst.power(-1, 0.2, 0.0),
    "float n": lambda: pst.power(30.0, 0.2, 0.0),
    "bool n": lambda: pst.power(True, 0.2, 0.0),
    "n beyond the float range": lambda: pst.power(pst.MAX_UNITS + 1, 0.2, 0.0),
    "negative w": lambda: pst.power(10, -0.1, 0.0),
    "negative l": lambda: pst.power(10, 0.2, -0.1),
    "w + l above 1": lambda: pst.power(10, 0.7, 0.4),
    "nan w": lambda: pst.power(10, math.nan, 0.0),
    "string w": lambda: pst.power(10, "0.2", 0.0),
    "sides 3": lambda: pst.power(10, 0.2, 0.0, sides=3),
    "sides 2.0": lambda: pst.power(10, 0.2, 0.0, sides=2.0),
    "alpha 0": lambda: pst.power(10, 0.2, 0.0, alpha=0),
    "alpha 1": lambda: pst.power(10, 0.2, 0.0, alpha=1),
    "alpha nan": lambda: pst.power(10, 0.2, 0.0, alpha=math.nan),
    "k above d": lambda: pst.sign_test_p(4, 3),
    "negative k": lambda: pst.sign_test_p(-1, 3),
    "sides 0 in p": lambda: pst.sign_test_p(1, 3, sides=0),
    "negative d": lambda: pst.min_wins_to_reject(-1),
    "alpha 1.5": lambda: pst.min_wins_to_reject(6, alpha=1.5),
    "target 0": lambda: pst.n_for_power(0.2, 0.0, target=0),
    "target above 1": lambda: pst.n_for_power(0.2, 0.0, target=1.2),
    "negative n_max": lambda: pst.n_for_power(0.2, 0.0, n_max=-1),
    "w + l above 1 in n_for_power": lambda: pst.n_for_power(0.8, 0.3),
    "negative loss ratio": lambda: pst.min_w_for_power(30, -0.5),
    "step 0": lambda: pst.min_w_for_power(30, 0.0, step=0),
    "step above 1": lambda: pst.min_w_for_power(30, 0.0, step=1.5),
    "negative n in min_w": lambda: pst.min_w_for_power(-3, 0.0),
    "d above n": lambda: pst.outcome_mass(5, 6, 0, 0.2, 0.1),
    "k above d in the mass": lambda: pst.outcome_mass(5, 3, 4, 0.2, 0.1),
}


@pytest.mark.parametrize("call", list(INVALID.values()), ids=list(INVALID))
def test_invalid_inputs_raise_value_error(call):
    with pytest.raises(ValueError):
        call()


def test_cli_writes_the_same_complete_report_twice(tmp_path):
    """One run as a script from another folder, one in-process: byte for byte the same file."""
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    run = subprocess.run([sys.executable, str(SCRIPT), "--out", str(first)],
                         cwd=tmp_path, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert pst.main(["--out", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    text = first.read_text(encoding="utf-8")
    report = json.loads(text)
    assert set(report) == {"model", "scenarios", "family_units", "min_w_at_n"}
    assert report["model"]["alpha"] == 0.05
    assert sorted(report["scenarios"]) == ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
    s1 = report["scenarios"]["S1"]
    assert [row["n"] for row in s1["power"]] == [6, 10, 20, 30, 38, 40, 50, 60]
    at_30 = next(row for row in s1["power"] if row["n"] == 30)
    assert at_30["two_sided"] == round(pst.power(30, 0.2, 0.0), 4)
    assert str(tmp_path) not in text


def test_cli_never_replaces_an_existing_report(tmp_path, capsys):
    out = tmp_path / "report.json"
    out.write_text("kept", encoding="utf-8")
    assert pst.main(["--out", str(out)]) == 1
    assert "already exists" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "kept"
