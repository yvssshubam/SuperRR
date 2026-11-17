# Results: v7 pressure definition

SupeRR Selector Season 2, Round 1 · tested 15 November 2026 · spec: "SupeRR Selector S2: v7 pressure definition brief" · run on top of the v6 code

> **Update, 16 Nov 2026.** Recomputed on 20 random splits with 50+ balls in each half (the method the report now uses), clutch repeatability is 0.08 / 0.13 for v5, 0.19 / 0.21 for v6 and **0.07 / 0.08 for v7** (batters / bowlers), not the 0.01 / −0.00 from 5 splits below. v7's clutch signal is weak rather than gone. The verdict does not change: v7 still does not beat v5 on condition 2 (batter spread 8.9 vs 12.7; bowler clutch 0.08 vs 0.13), and it still fails conditions 3 and, for batters, 4.

## Verdict

v7 fixes what it set out to fix. Its pressure balls are almost never from decided games or free swings, and players change their behaviour on them far more than on v5's. But it **loses the pressure-specific signal**: how much better or worse a player does under pressure than usual no longer repeats between two halves of the matches. It also leaves too few batters to rank. **v7 fails the four-condition rule for both roles, and v5 stays the submitted model.**

| Condition (fixed before the run) | Batters | Bowlers |
|---|---|---|
| 1. Beats v5 on check 4 (behaviour shift) | **Pass**: 6.9 vs 2.7 points | **Pass**: 3.3 vs 2.9 points |
| 2. Beats v5 on check 5 (spread **and** clutch repeatability) | **Fail**: spread 8.9 vs 12.7, clutch 0.01 vs 0.08 | **Fail**: spread 9.6 vs 8.7 passes, but clutch −0.00 vs 0.03 |
| 3. Top 10 at least as stable as v5 (bootstrap) | **Fail**: 69% vs 71% | **Fail**: 57% vs 61% |
| 4. At least 60 players eligible | **Fail**: 41 | **Pass**: 92 |
| **Adopt** | **No** | **No** |

## 1. The rules as run

All numbers were fixed before any list was looked at, as the brief specifies.

| Part | Rule as run |
|---|---|
| **Batter pressure ball** | Faced; batting win chance 10–90%; `fc_bat_max` ≥ **8.15 points**; and ≤ 2 proper batters to come or ≤ 30 balls left |
| **Batter rating unit** | His pressure balls plus the balls he faced earlier in that innings while the result was open; nothing after his last pressure ball |
| **Bowler pressure over** | At its first ball: bowling win chance 10–90% and `fc_bowl_max` ≥ **2.60 points**; every ball of the over counts |
| Bar values | Batters **8.15** win-probability points (the v6 cut; the brief's "8.2" is this value rounded). Bowlers **2.60** points (the v6 single cut: top 25% of all bowler balls, one cut across both innings) |
| Proper batter | Usual position 1–7 = median `batting_order` over his innings in the kept matches; with fewer than 3 innings, his listed position in that match's playing XI |
| Still to come | Proper batters in the batting side's played XI who have not yet appeared as striker or non-striker in the innings; impact substitute counted, replaced player dropped |
| Quotas | None, for either role |
| Removed (as in v6) | Knockout ×1.2, psychological pooling |
| Unchanged | Failure-cost indexes, win model, run value, same-situation comparison, opposition adjustment, shrinkage, component weights, eligibility (120 balls in pressure units, 10 matches, active in the last 12 months), `pressure_li`, the reporting-bug fix |

**Depth count, checked by eye on five real balls** (all correct by the rule):

| Situation | Proper batters to come |
|---|---:|
| RR v CSK 2026, chase over 2, 19/0, Jaiswal and Sooryavanshi in; Jurel, Parag, Hetmyer, Jadeja to come (Archer usually bats 8) | 4 |
| GT v LSG 2022, over 10, 51/3, Miller just in; only Tewatia (6) left among proper batters | 1 |
| West Indies v Australia 2022, over 9, 60/2; Holder (7) and Powell (5) to come, then bowlers | 2 |
| Zimbabwe v Ireland 2023, over 18, 118/5; only bowlers left | 0 |
| SRH v KKR 2023, over 7, 55/4, impact sub Tripathi already out; Samad (7) to come, Natarajan (replaced) not counted | 1 |

Across all balls, 44% have 2 or fewer proper batters to come. Many XIs carry only six proper batters, so the depth rule often triggers at three or four down.

## 2. Checks 1–8, v5 v6 v7 side by side

| Check | Batters v5 | Batters v6 | Batters v7 | Bowlers v5 | Bowlers v6 | Bowlers v7 |
|---|---:|---:|---:|---:|---:|---:|
| Share of balls rated as pressure | 25% | 50% | **14%** | 25% | 25% | 24% |
| 1. Top 10 pressure overs look like pressure | yes | yes | yes, tail-enders in last-wicket chases | yes | yes | yes, last overs of close chases |
| 2. Rated balls in lost or decided games | 2.2% | 10.5% | **0.0%** | 2.2% | 2.9% | 3.3% |
| 3. Free swings among rated batter balls | 40.6% | 32.8% | **8.3%** | | | |
| 3. Free swings among pressure balls only | 40.6% | 41.7% | **0.4%** | | | |
| 4. Behaviour shift, total (pp) | 2.7 | 4.3 | **6.9** | 2.9 | 1.9 | **3.3** |
| 4. Shift in dismissal / error rate (pp) | −0.04 | −1.13 | **−3.25** | +0.26 | −0.03 | **+0.62** |
| 5. Spread of pressure-specific ability (runs/100) | 12.7 | 12.6 | 8.9 | 8.7 | 13.5 | 9.6 |
| 5. Clutch repeatability (5 splits, 30+ balls) | 0.08 | 0.18 | **0.01** | 0.03 | 0.19 | **−0.00** |
| 6. Pressure rating repeatability | 0.31 | 0.32 | 0.25 | 0.33 | 0.41 | 0.35 |
| 6. Full score repeatability | 0.31 | 0.32 | 0.25 | 0.26 | 0.36 | 0.27 |
| 6. Mean bootstrap top-10 share of the picks | 71% | 66% | 69% | 61% | 66% | 57% |
| 6. Picks in the top 10 in 70%+ of resamples | 5 | 4 | 5 | 4 | 5 | 2 |
| 7. Held-out prediction, own target (information only) | 0.17 | 0.17 | 0.15 | 0.14 | 0.27 | 0.18 |
| 8. Top 10 kept from v5 | 10 | 7 | **5** | 10 | 8 | 8 |
| 8. Rank correlation with v5, all eligible | 1.00 | 0.93 | 0.96 | 1.00 | 0.88 | 0.91 |
| Eligible players | 107 | 128 | **41** | 107 | 93 | 92 |

Checks 2 and 3 are reported but do not count as evidence: the open-result and depth rules make v7 pass them by construction.

**What the checks say, in plain words:**

- **The flagged moments are cleaner.** No v7 batter pressure ball comes from a decided game (0.0%), and almost none are free swings (0.4%).
- **Players react to them.** On v7 pressure balls, batters are out 3.25 points less often and play 2.75 points fewer dots than on their other balls in the same phase. Bowlers bowl 0.62 points more wides, no-balls and full tosses, the first sign of bowlers cracking in any version.
- **But the clutch signal disappears.** Under v7, how much better a player does under pressure than usual does not repeat between halves of the matches (0.01 batters, −0.00 bowlers). v6 had 0.18–0.19. The stricter rules leave so few balls per player that the pressure-specific part becomes noise. The rating then leans more on each player's usual level (β 0.81 batters, 1.12 bowlers).
- **The lists get less stable.** Only 2 of the 10 v7 bowlers are in the top 10 in 70% of resamples, against 4 in v5.

## 3. Answers to the five extra questions

**1. The 0.03 against 0.29 mismatch (v5 bowler clutch repeatability).** Neither number is a fair summary. Each came from a different and limited test.

| Method | Batters | Bowlers |
|---|---:|---:|
| One odd/even split, 50+ balls each half (README 8.1) | 0.10 | **0.29** |
| One odd/even split, 30+ balls | 0.15 | 0.26 |
| 5 random splits, 30+ balls (v6 results) | 0.08 | **0.03** |
| 5 random splits, 50+ balls | 0.06 | 0.05 |
| **20 random splits, 50+ balls (best estimate)** | **0.08** (−0.10 to 0.25) | **0.12** (0.01 to 0.22) |

The README's 0.29 is a single split that happens to be higher than all 20 random splits. The v6 results' 0.03 came from only five splits with a lower ball floor. The best estimate is **0.12 for bowlers and 0.08 for batters**. Clutch is weak but not zero. **The README is now corrected** (section 8.1 states the 20-split averages). The v6 and v7 comparisons in this file all use the same 5-split, 30+ method, so they are like for like with each other.

**2. Chase share.** v7 is almost entirely chases, so clutch under v7 partly means "better in chases".

| | v5 | v6 | v7 |
|---|---:|---:|---:|
| Batter pressure balls in the second innings | 48% | 80% | **84%** |
| Bowler pressure-over balls in the second innings | 48% | 48% | **96%** |

**3. Sample size.** Batting falls below the brief's floor of 60 eligible players.

| | Eligible | Median pressure balls | Median balls in pressure units |
|---|---:|---:|---:|
| Batters v5 | 107 | 210 | 210 |
| Batters v6 | 128 | 202 | 391 |
| Batters v7 | **41** | **137** | 204 |
| Bowlers v5 | 107 | | 234 |
| Bowlers v6 | 93 | | 254 |
| Bowlers v7 | 92 | | 244 |

**4. Bowling mix.** v7 restores some powerplay pressure (31%, against 12% in v6) but not the death overs (19%, against 47% in v5). First-innings overs almost vanish (4%), as the brief expected and accepted.

| | Powerplay | Middle | Death | First innings |
|---|---:|---:|---:|---:|
| v5 | 32% | 21% | 47% | 52% |
| v6 | 12% | 60% | 28% | 52% |
| v7 | 31% | 50% | 19% | 4% |

**Batting depth on v7 pressure balls:** on average 1.0 proper batter is still to come. 69% qualify through depth alone, 1% through the last five overs alone, and 30% through both.

**5. Who moved** (v5 → v7 top 10):

| Player | Move | What in the rules moved him |
|---|---|---|
| Vaibhav Sooryavanshi | Out, not eligible | Opener: only 5% of his balls have 2 or fewer proper batters to come; 0 pressure balls |
| Abhishek Sharma | Out, not eligible | Opener: 3% of his balls pass the depth rule; 56 balls counted |
| Phil Salt | Out, not eligible | Opener: 179 balls counted, but they come from only 7 matches (10 needed) |
| Finn Allen | Out, not eligible | Opener: 8 balls counted |
| Rajat Patidar | Out, not eligible | Bats 4 in a deep line-up; 47 balls counted |
| Harry Brook | In at 5 | Middle order: qualifies on depth (122 balls); his pressure rating (18.3) is below his usual level (30.1) |
| Romario Shepherd | In at 6 | Finisher: his balls come with few batters left (156 balls) |
| Cameron Green | In at 8 | Middle order (129 balls) |
| Rovman Powell | In at 9 | Finisher (324 balls) |
| Rinku Singh | In at 10 | Finisher (284 balls) |
| Jasprit Bumrah | Out, to 12th | His pressure overs are mostly at the death of chases; 352 balls; his rating rose (20.3 → 22.5) but two spinners passed him |
| Mustafizur Rahman | Out, to 15th | Death bowler; fewer overs clear the bar (310 balls) |
| Mitchell Santner | In at 3 (from 18th) | Left-arm spinner in the middle overs of open chases; 488 balls; clutch Δ +13.9 |
| Axar Patel | In at 5 (from 21st) | Same profile; clutch Δ +15.1 on a usual level of only 2.4 |

## 4. The lists under v7

Submitted lists (players who cannot play in the IPL removed, as in v5; this removes Mohammad Nawaz, 3rd, and Abrar Ahmed, 7th, from the bowling list).

**Batters:**

| v7 | Batter | v5 | v6 | Pressure rating | Usual level | Clutch Δ | Balls counted | In top 10 (bootstrap) |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Suryakumar Yadav | 4 | 3 | 33.9 | 28.4 | 10.8 | 360 | 100% |
| 2 | Tim David | 3 | 4 | 27.6 | 28.2 | 4.7 | 396 | 94% |
| 3 | Heinrich Klaasen | 6 | 9 | 25.1 | 24.0 | 5.5 | 211 | 96% |
| 4 | Tilak Varma | 7 | 14 | 18.8 | 18.4 | 3.8 | 585 | 82% |
| 5 | Harry Brook | not eligible | 5 | 18.3 | 30.1 | −6.2 | 122 | 61% |
| 6 | Romario Shepherd | 12 | 16 | 18.2 | 24.5 | −1.8 | 156 | 61% |
| 7 | Shreyas Iyer | 10 | 7 | 17.0 | 15.7 | 4.3 | 256 | 71% |
| 8 | Cameron Green | 18 | 15 | 14.3 | 15.3 | 1.9 | 129 | 48% |
| 9 | Rovman Powell | 17 | 19 | 13.9 | 7.8 | 7.6 | 324 | 43% |
| 10 | Rinku Singh | 30 | 20 | 12.6 | 11.3 | 3.4 | 284 | 37% |

**Bowlers:**

| v7 | Bowler | v5 | v6 | Pressure rating | Usual level | Clutch Δ | Balls counted | In top 10 (bootstrap) |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Rashid Khan | 1 | 2 | 33.3 | 16.6 | 14.7 | 607 | 96% |
| 2 | Sunil Narine | 2 | 1 | 31.0 | 28.1 | −0.4 | 403 | 85% |
| 3 | Mitchell Santner | 18 | 18 | 23.4 | 8.5 | 13.9 | 488 | 56% |
| 4 | Kuldeep Yadav | 4 | 5 | 24.3 | 16.4 | 6.0 | 499 | 56% |
| 5 | Axar Patel | 21 | 25 | 17.8 | 2.4 | 15.1 | 540 | 58% |
| 6 | Josh Hazlewood | 7 | 4 | 22.4 | 10.7 | 10.4 | 392 | 55% |
| 7 | Bhuvneshwar Kumar | 6 | 55 | 28.3 | 26.9 | −1.7 | 472 | 47% |
| 8 | Wanindu Hasaranga | 3 | 3 | 25.2 | 25.0 | −2.7 | 504 | 49% |
| 9 | Varun Chakravarthy | 5 | 7 | 23.3 | 22.5 | −1.9 | 542 | 36% |
| 10 | Krunal Pandya | 8 | 6 | 17.8 | 8.7 | 8.1 | 386 | 28% |

Spinners: 6 in v5, 7 in v6, **8 in v7**.

## 5. Information-only variants

Not candidates. Overlap with the v7 top 10 only. Eligible counts exclude players who cannot play in the IPL. The depth variants change batters only, so the bowler columns repeat the main rule.

| Variant | Batters eligible | Batters kept of v7 top 10 | Bowlers eligible | Bowlers kept of v7 top 10 |
|---|---:|---:|---:|---:|
| Proper batters to come ≤ 1 | 28 | 6 | 86 | 10 |
| Proper batters to come ≤ 3 | 66 | 7 | 86 | 10 |
| No depth rule (cost and open result only) | 116 | 5 | 86 | 10 |
| Open band 5–95% | 43 | 10 | 88 | 9 |

The depth rule drives the batting list: with it set at 3, 66 batters qualify (above the floor of 60), and without it the list keeps only 5 of the v7 top 10.

## 6. What differed from the brief, and why

- **Batter bar 8.15, not 8.2.** The brief defines the bar as the v6 cut; 8.2 is that value rounded.
- **Players with fewer than 3 innings and no listed position** in the XI count as not proper batters. The brief does not cover this case; they are almost always bowlers.
- **11 innings** list 13–20 played players in the XI (data quirks). They are used as given; only proper batters count.
- **The impact substitute is in the pool from the first ball,** even before he came on. As the brief notes, this uses hindsight.
- **Variant eligible counts** exclude players who cannot play in the IPL, matching the submitted lists.
- **Check 7** compares each model with its own pressure target, so the numbers are not a like-for-like contest (information only, as the brief says).

## 7. What this means

1. **v5 stays the submission.** v7 fails conditions 2 and 3 for both roles, and condition 4 for batters.
2. **v6 and v7 pull in opposite directions.** v6 had the stronger clutch signal (0.18–0.19) but flagged many decided-game and free-swing balls. v7 cleans up the flagged moments, but each player is left with too few of them to measure clutch. A definition that is both clean and well-sampled is not available in this data.
3. **For the v5 report's limitations** (whatever is submitted):
    - About 4 in 10 of v5's batter pressure balls are free swings (40.6%).
    - v5's clutch Δ repeats weakly: 0.08 for batters and 0.12 for bowlers over 20 random splits. The lists lean on each player's usual level.
4. **v7's real finding is worth one line in the report:** bowlers make more errors in genuinely tight overs (+0.62 points), and batters protect their wicket (−3.25 points). That is direct evidence that pressure changes behaviour, which neither v5 nor v6 showed.

## 8. Reproduce

The v7 code is a copy of the v6 code plus `02b_depth_v7.py` (depth count and v7 flags), the `"v7"` option of `PRESSURE_DEF` in `03_ratings.py`, and `experiments/v7_compare.py`.

```
python 01_state.py <data> out
python 02_pressure.py out
python 02b_depth_v7.py out <data>
python 03_ratings.py out 300
python 05_final_tables.py out <data>
python experiments/v7_compare.py out <v6_out> <v5_out> <data>
```

Seeds: bootstrap 42 (300 resamples); check-5/6/7 splits 5; extra question 1 uses 20 splits (seed 21).
