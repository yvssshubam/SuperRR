# Results: testing a cost-of-failure pressure definition (v6)

SupeRR Selector Season 2, Round 1 · tested 15 November 2026 · spec: "SupeRR Selector S2: Revising the pressure definition"

## Verdict

The cost-of-failure definition **measures pressure-specific skill more reliably than the leverage flag**, above all for bowlers, but **it does not make the rankings better** by the rules fixed before the test. **v5 (leverage flag) stays as the submitted model.** v6 is reported as a tested alternative.

| | Batters | Bowlers |
|---|---|---|
| More reliable measurement? | Partly (clutch repeatability 0.08 → 0.18) | **Yes** (clutch 0.03 → 0.19, rating 0.33 → 0.41) |
| Better behaviour signal? | Yes | No (error rate does not shift) |
| Fewer lost causes and dead games? | **No** (2.2% → 10.5%) | No (2.2% → 2.9%) |
| More stable top 10? | No (71% → 66%) | Yes (61% → 66%) |
| Adopted? | **No** | **No** |

## 1. What was tested

The spec replaces "top 25% of the Leverage Index in each innings" with a role-specific cost of failure, judged over the whole stay at the crease (batters) or the whole over (bowlers).

**Rules, fixed before any list was looked at:**

| Part | Rule |
|---|---|
| Batter failure cost | Fall in the batting side's win chance if he is out (`fc_wkt`) or plays a dot (`fc_dot`); the worse of the two (`fc_bat_max`). Not weighted by how likely each outcome is |
| Bowler failure cost | Fall in the bowling side's win chance if the ball goes for four (`fc_four`) or is a no-ball (`fc_extra`, never cheaper than a wide); the worse of the two (`fc_bowl_max`) |
| Ball-level flag | Top 25% of each role's balls. Batters: one cut across both innings. Bowlers: cut within each innings (a single cut flags only 2% of first-innings bowling) |
| Rating unit, batters | A **pressure innings** is one with at least one flagged ball; every ball of it counts |
| Rating unit, bowlers | A **pressure over** is one whose first ball is in the top 25% of over starts in that innings; every ball of it counts |
| Removed | Knockout ×1.2; bowler psychological pooling |
| Unchanged | Win-probability model, run value, same-situation comparison, opposition adjustment, shrinkage, component weights, eligibility floor (120 balls inside pressure units, 10 matches, active in the last 12 months) |
| Kept for comparison | The old flag, as `pressure_li` |
| Fixed | The reporting bug: bowlers' published pressure stats (`balls_P`, `econ_P`, `pb_IPL`, `pb_T20I`) counted pooled balls; they now use real pressure balls |

**Adoption rule (set before checks 4–8 were run):** adopt for a role only if the new definition beats the old on both check 4 (behaviour shift) and check 5 (pressure-specific signal), and is not worse on checks 2–3.

## 2. Step 1: ball-level checks 1–3

Old flag against the new ball-level flags, before any rating changed.

**Where the flags land:**

| Role | Definition | 1st innings | Powerplay | Middle | Death | Share of 1st-innings balls flagged |
|---|---|---:|---:|---:|---:|---:|
| Batters | Leverage (old) | 52% | 33% | 21% | 46% | 24.9% |
| Batters | Failure cost, max | 20% | 50% | 40% | 11% | 9.6% |
| Batters | Failure cost, sum | 14% | 44% | 42% | 14% | 6.5% |
| Bowlers | Leverage (old) | 52% | 32% | 21% | 47% | 25.0% |
| Bowlers | Failure cost, max (one cut) | 4% | 30% | 49% | 21% | 2.1% |
| Bowlers | Failure cost, max (per innings) | 52% | 13% | 60% | 27% | 25% |

**Check 1, face validity.** Batters' top-20 overs under the new index are last-wicket chase finishes (9 down, few needed). Under the old flag they are last overs of big chases, some at 11–14% win chance. Bowlers' top 20 are last overs of close chases under both. *Pass.*

**Check 2, lost causes and dead games** (own side under 10% or over 90% to win):

| | Old | New (max) | New (sum) |
|---|---:|---:|---:|
| Batters | 2.2% | 0.5% | 0.8% |
| Bowlers, one cut | 2.2% | 4.5% | 4.8% |
| Bowlers, per innings | 2.2% | 1.4% | |

*Batters pass. Bowlers pass only with the per-innings cut.*

**Check 3, free swings** (share of flagged batter balls):

| | Old | New (max) | New (sum) |
|---|---:|---:|---:|
| 1st innings, death, 6+ wickets in hand | 10.9% | 0.0% | 0.0% |
| Powerplay, 9+ wickets in hand | 29.7% | **41.7%** | **36.5%** |

*Fails on the powerplay.* The win model says an early chase wicket costs 8.3 win-probability points on average, more than a middle-overs wicket (6.4). The flag threshold is 8.2 points, so 57.5% of chase-powerplay balls with 9+ wickets in hand are flagged. Cost of failure looks only at the downside, and the downside of an early wicket is genuinely large. The spec's "opportunity" idea is about the upside, which this index does not see.

## 3. Ball-level checks 4–5

Same player, innings and phase; flagged minus unflagged, in percentage points.

| Role | Definition | Dismissal | Dot | Boundary | Error | Boundary conceded |
|---|---|---:|---:|---:|---:|---:|
| Batters | Leverage (old) | −0.04 | −1.98 | +0.66 | | |
| Batters | Failure cost, max | −0.53 | −0.05 | −1.02 | | |
| Bowlers | Leverage (old) | | −1.96 | | +0.26 | +0.57 |
| Bowlers | Failure cost, max, per innings | | +0.44 | | −0.19 | −1.89 |

On old-flag balls batters attack; on new-flag balls they play safe. Neither flag shows players cracking, and the bowlers' error rate barely moves under either.

| Role | Definition | Spread of pressure-specific ability (runs/100) | Clutch repeatability | Rating repeatability |
|---|---|---:|---:|---:|
| Batters | Leverage (old) | 12.7 | 0.08 | 0.31 |
| Batters | Failure cost, max | 14.7 | 0.22 | 0.28 |
| Bowlers | Leverage (old) | 10.0 | 0.03 | 0.31 |
| Bowlers | Failure cost, max, per innings | 13.7 | 0.20 | 0.40 |

Repeatability: rate players on one random half of the matches and again on the other half, then correlate (mean of 5 splits). 0 is pure noise.

## 4. Whole-model run: checks 2–8

Full pipeline on the v6 definition (Readiness ratings, 300-sample bootstrap, final tables), against v5 as submitted.

| Check | Batters v5 → v6 | Bowlers v5 → v6 |
|---|---|---|
| Share of balls rated as pressure | 25% → 50% | 25% → 25% |
| 2. Rated balls in lost or decided games | 2.2% → 10.5% ✗ | 2.2% → 2.9% ✗ |
| 3. Free swings among batter pressure balls | 40.6% → 32.8% ✓ | |
| 4. Total behaviour shift (pp) | 2.7 → 4.3 ✓ | 2.9 → 1.9 ✗ |
| 4. Shift in dismissal / error rate (pp) | −0.04 → −1.13 | +0.26 → −0.03 |
| 5. Spread of pressure-specific ability | 12.7 → 12.6 = | 8.7 → 13.5 ✓ |
| 5. Clutch repeatability | 0.08 → 0.18 ✓ | 0.03 → 0.19 ✓ |
| 6. Pressure rating repeatability | 0.31 → 0.32 = | 0.33 → 0.41 ✓ |
| 6. Full score repeatability | 0.31 → 0.32 = | 0.26 → 0.36 ✓ |
| 6. Mean bootstrap top-10 share of the picks | 71% → 66% ✗ | 61% → 66% ✓ |
| 6. Picks in the top 10 in at least 70% of resamples | 5 → 4 ✗ | 4 → 5 ✓ |
| 7. Held-out prediction of own pressure target (information only) | 0.17 → 0.17 = | 0.14 → 0.27 ✓ |
| 8. Top 10 kept | 7 of 10 | 8 of 10 |
| 8. Rank correlation, all eligible players | 0.93 | 0.88 |
| Eligible players | 107 → 128 | 107 → 93 |

Check 7 is information only, as the spec asks: each model predicts its own pressure target, so the two numbers are not a like-for-like contest.

**Against the adoption rule:**

| | Check 4 | Check 5 | Checks 2–3 | Adopt? |
|---|---|---|---|---|
| Batters | Pass | Pass (clutch only) | Worse on lost causes | No |
| Bowlers | Fail | Pass | Slightly worse on lost causes | No |

## 5. The lists under v6

Submitted Readiness lists (players who cannot play in the IPL removed, as in v5).

**Batters:**

| v6 rank | Batter | v5 rank | Pressure rating | Usual level | Clutch Δ | Balls in pressure innings | In top 10 (bootstrap) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | Abhishek Sharma | 2 | 41.1 | 28.2 | 26.1 | 1,429 | 99% |
| 2 | Vaibhav Sooryavanshi | 1 | 40.1 | 38.5 | 19.7 | 401 | 92% |
| 3 | Suryakumar Yadav | 4 | 32.4 | 29.2 | 16.9 | 1,178 | 97% |
| 4 | Tim David | 3 | 28.2 | 29.0 | 12.8 | 566 | 80% |
| 5 | Harry Brook | not eligible | 24.0 | 23.5 | 11.5 | 254 | 47% |
| 6 | Phil Salt | 5 | 22.4 | 24.2 | 9.6 | 1,112 | 60% |
| 7 | Shreyas Iyer | 10 | 22.0 | 8.5 | 17.5 | 985 | 57% |
| 8 | Reeza Hendricks | 11 | 21.2 | −4.7 | 23.7 | 554 | 50% |
| 9 | Heinrich Klaasen | 6 | 20.8 | 27.1 | 6.5 | 440 | 43% |
| 10 | Josh Inglis | 21 | 18.7 | −11.4 | 24.8 | 582 | 36% |

Out: Tilak Varma (v6 rank 14), Rajat Patidar (12), Finn Allen (17). Their pressure ratings fall once every ball of their pressure innings counts (Tilak 28.4 → 15.6, Allen 27.5 → 14.5).

**Bowlers:**

| v6 rank | Bowler | Type | v5 rank | Pressure rating | Usual level | Clutch Δ | Balls in pressure overs | In top 10 (bootstrap) |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | Sunil Narine | Spin | 2 | 38.5 | 24.7 | 16.8 | 279 | 98% |
| 2 | Rashid Khan | Spin | 1 | 33.3 | 18.4 | 17.2 | 628 | 98% |
| 3 | Wanindu Hasaranga | Spin | 3 | 32.4 | 19.9 | 14.9 | 659 | 85% |
| 4 | Josh Hazlewood | Pace | 7 | 27.4 | 12.3 | 16.6 | 274 | 70% |
| 5 | Kuldeep Yadav | Spin | 4 | 33.7 | 11.4 | 23.6 | 536 | 80% |
| 6 | Krunal Pandya | Spin | 8 | 22.4 | 9.6 | 14.0 | 244 | 62% |
| 7 | Varun Chakravarthy | Spin | 5 | 24.3 | 20.5 | 6.3 | 446 | 54% |
| 8 | Mustafizur Rahman | Pace | 10 | 21.2 | 12.2 | 10.4 | 581 | 52% |
| 9 | Mujeeb Ur Rahman | Spin | 11 | 17.9 | 4.1 | 14.3 | 254 | 38% |
| 10 | Jamie Overton | Pace | not eligible | 20.5 | 4.1 | 16.8 | 142 | 21% |

Out: Bhuvneshwar Kumar (v6 rank 55), Jasprit Bumrah (13). Spinners: 6 in v5, 7 in v6.

## 6. Why the results look like this

- **Batters: whole innings brings in decided balls.** Once an innings contains one pressure ball, every ball counts, including those after the game was settled. Lost causes and dead games rise to 10.5%, and pressure innings cover half of all batter balls.
- **Batters: powerplay wickets are expensive in the win model.** Cost of failure keeps flagging openers early in chases; the whole-innings unit only partly offsets this (free swings 40.6% → 32.8%).
- **Bowlers: pressure moves to the middle overs.** A pressure over is judged when the bowler is handed the ball. Many death overs come after the match is decided, where a four costs little, while middle overs of close games are where the result is open. 60% of pressure overs are middle overs, against 21% before. That is the opposite of the spec's expectation of a shift towards death-over pacers, and it is why Bhuvneshwar (powerplay and death specialist) falls from 6th to 55th.
- **Bowlers: the signal is sharper.** Clutch performance goes from noise (0.03) to repeatable (0.19), the full score repeats better (0.26 → 0.36), and the picks are more stable in the bootstrap.

## 7. Decision and what it means for the report

1. **Submit v5.** The adoption rule was fixed before the results; neither role meets it. Changing the rule after seeing check 5 would be moving the goalposts.
2. **Report v6 as a tested alternative.** One slide and a README section: *"A cost-of-failure definition makes clutch performance repeatable (bowlers 0.19 vs 0.03) where the leverage flag mostly measured noise. It was not adopted: it did not change behaviour more than the leverage flag for bowlers, it rates more balls from decided games, and it shifts bowling pressure away from the death overs."*
3. **The reporting bug is real** and is fixed in v6; it does not change any ranking. It should also be fixed in v5's descriptive tables.
4. **Most promising next step:** the bowler over-level failure cost, with a rule that excludes overs where the match is already decided at the start of the over, tested against the same rule set.

## 8. Reproduce

The v6 code is a copy of the v5 repository with these changes: `02_pressure.py` (failure-cost indexes, pressure innings and overs, entry win chance), `03_ratings.py` (`PRESSURE_DEF` switch, pooling off, reporting fix), and three new scripts.

```
python 01_state.py <data> out
python 02_pressure.py out
python experiments/pressure_def_checks.py out <data>    # checks 1-3, ball level
python experiments/pressure_gate.py out                 # checks 4-5, ball level
python 03_ratings.py out 300
python 05_final_tables.py out <data>
python experiments/v6_compare.py out <v5_out>           # checks 2-8, whole model, v5 vs v6
```

Seeds: bootstrap 42 (300 resamples), repeatability and held-out splits 5. Data: the supplied data pack only.
