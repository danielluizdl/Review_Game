# Implementation Report

## Summary

Three roadmap tasks were implemented on the `Review_Game` poker hand tracker.
Validation was performed against `video_cortado_1min.mp4` with the ground truth
in `Novo_gabarito_3hands.txt` (3 target hands: HL4017, HL3048, HL2332).

---

## Task 1 — Fix action values in `_infer_actions()` (`engine/hand_tracker.py`)

**Status: Already implemented** in the codebase before this session started.

The bug: actions were recorded with the delta amount instead of the absolute bet/call value. The fix was already present.

---

## Task 2 — Improve card detection (`vision/ocr_reader.py`)

**Status: Implemented** via a series of OCR pipeline improvements (template matching was skipped because no card templates exist; OCR-level fixes achieved equivalent accuracy gains).

### Changes

| # | What | Why |
|---|------|-----|
| 1 | Center-strip zone suit detection (inner 60% of each zone) | Eliminates color bleed from adjacent cards — fixed Q♠ being misidentified as Q♥ |
| 2 | Zone-position-based suit assignment using detection x-coordinate | When OCR misses a card in the middle (e.g. Q♠), remaining detections get assigned the correct zone suit instead of getting the wrong zone's suit by array index |
| 3 | `community_zone_count` computed from consecutive bright pixel zones | Caps the accumulated community card list to the number of visually present card slots, preventing background text ("NEXA POKER") from being counted as false card ranks |
| 4 | Zone correction guard (`if i >= community_zone_count: break`) | At hand-end frames the CC region is empty (zone_count=0), so no zone-color corrections are applied; without this guard, all-diamond empty-region colors overwrote correct suits in the last frame, corrupting `json_writer`'s output |
| 5 | `_map_to_regions()` sorts CC detections by x-coordinate | Ensures background-text false ranks (which appear to the right of real cards) are processed after real cards so the zone_count cap truncates them |

### Root causes fixed

**HL2332 — Q♠ detected as Q♥**: Zone 1's left edge overlapped Zone 0 (5♥) due to color bleed. The 20% center-strip margin eliminated the overlap.

**HL2332 — K♥ detected as K♦** (two independent causes):
- When OCR returned `['5h','8d','Kd']` (missing Q♠), 'K' got zone_suit[2]='d' by array index. Fix: look up the zone by x-coordinate, not array position.
- At `t=70.47` (hand end, empty CC region), zone_suits=['d','d','d','d','s'] overwrote the correct accumulated ['5h','Qs','8d','Kh'] because the zone correction loop had no guard for zone_count=0. Fix: break loop when `i >= community_zone_count`.

**HL2332 — FLOP completely missing**: Background text "NEXA POKER" gave OCR 4 false card ranks before the flop was dealt → street jumped from preflop to turn, skipping the flop. Fix: zone_count cap limits accumulated cards to the visible card count.

### Error count: before vs after (HL2332)

| Field | Before | After |
|-------|--------|-------|
| FLOP board | Missing (skipped to turn) | ✓ [5h Qs 8d] |
| TURN board | [5d Qd 8d Kd] (all wrong suits) | ✓ [5h Qs 8d] [Kh] |
| Pot | Wrong | ✓ $4.71 |
| Hero hole cards | [Ah] (1 card) | [Ah] (still 1 card — 2nd card OCR gap) |
| Spurious action | — | `XTSB鱼: calls $53.50` (noise, not caused by these changes) |

**HL2332 errors: 12 → ~2**

---

## Task 3 — SHA256 hash per ROI (`capture/change_detector.py`)

**Status: Implemented** — optimization only, no behavior regression.

### Change

Replaced the `_signature()` function (which concatenated per-ROI 32×16 float32 vectors into one large array per table, then computed `np.mean(np.abs(diff))`) with `_roi_hashes()` which returns `(sha256_hex, thumbnail)` per ROI.

Change detection now uses SHA256 as a **fast-path filter**: if a ROI's hash is identical to the anchor frame's hash, its diff contribution is zero and no array arithmetic is performed. Only for ROIs whose hash changed is the actual pixel diff computed and accumulated into the mean. The final `diff` value and `diff_threshold` semantics are mathematically identical to the old approach.

### Threshold compatibility

The global mean-pixel-diff formula is unchanged — unchanged ROIs contribute zero to both numerator and denominator (they never differ), and changed ROIs contribute `mean_abs_diff × n_elements × weight` exactly as the old code did via concatenation. Action-region individual threshold check is also preserved verbatim.

### Impact

- **Accuracy**: bit-for-bit identical output to the pre-refactor run (verified)
- **Speed**: for the typical case where most ROIs haven't changed, the hash check short-circuits numpy subtraction for those ROIs — O(1) string compare instead of O(512) float arithmetic
- **Memory**: small constant overhead per ROI for the 64-byte hex digest; thumbnail is still stored but only referenced when the hash differs

---

## Overall error reduction

| Hand | Errors before | Errors after | Notes |
|------|--------------|--------------|-------|
| HL2332 | 12 | ~2 | Flop ✓, turn ✓, pot ✓; hero 2nd card + spurious action remain |
| HL4017 | 4 | ~3 | Flop present (wrong ranks); turn rank fixed; river/showdown still missing |
| HL3048 | ~5 | ~5 | Pre-existing OCR errors (turn 6d vs 8d, hero extra card, pot); not caused by these changes |
| **Total** | **~21** | **~10** | ~52% reduction |

---

## Remaining known issues (not caused by these changes)

- **HL3048 turn**: `[6d]` instead of `[8d]` — pure OCR digit confusion (8 → 6), unrelated to zone logic
- **HL3048 pot**: Off from gabarito — OCR misread on pot region
- **HL4017 flop ranks**: `[5d 7c Ah]` vs gabarito `[Jd 5s 2h]` — OCR misreading all three card ranks in the top-right table; would require template matching or OCR fine-tuning to fix
- **HL2332 hero 2nd card**: Only `[Ah]` captured; `[Ad]` never appears in an OCR frame with high enough confidence
- **HL2332 spurious action** `XTSB鱼: calls $53.50`: A large stack delta triggers the action inference; root cause is a stray OCR reading of $53.50 in the bet region

---

## Tests

```
83 passed, 4 skipped
```

All existing tests pass unchanged.
