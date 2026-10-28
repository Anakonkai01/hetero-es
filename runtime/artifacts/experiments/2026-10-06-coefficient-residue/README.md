# Coefficient residue and record size, 2026-10-06

Evidence for one decision: the coefficients of an ES update are computed ONCE by the coordinator and travel inside the
generation record; nobody recomputes them (ADR-002, "Why the coefficients travel"; numerical contract section 13).

Run (about 3 seconds, fixed seeds, 5070 Ti box, conda env `ai`: Python 3.12.13, NumPy 2.4.5):

```bash
python measure.py > output.txt
```

## What it shows (all numbers are in `output.txt`)

1. **A generation record is small:** 744 bytes for 8 candidates, 1,883 for 32, 6,747 for 128 (the FP16 model is 0.99 GB).
2. **The coefficients are not stable across summation orders.** With rewards k/96 (as in the learning pilot) and the
   reward standardization of `standardize_rewards`, another order of the float64 sums changed the float32 coefficients
   in 0.40% (N = 8), 0.30% (N = 16) and 0.34% (N = 64) of 20,000 random sets each. **Every** one of those changes was of
   the same kind: a coefficient that is `0.0` in one order and a residue of about 1e-16 in the other (this happens when a
   reward equals the mean exactly, which is common with k/96 rewards). An exactly rounded mean and standard deviation
   (`math.fsum`) disagrees with the NumPy result at a similar rate, so it is not a NumPy defect: it is the rounding of
   the mean.
3. **That residue does not change the weights in a synthetic test:** two coefficient vectors differing only by residues of
   about 1e-17, 2,000,000 elements, NumPy only: 0 FP32 direction elements and 0 FP16 weights differ.

## What it does NOT show

- It does not use `apply_es_update_` or the real model, only NumPy on random numbers.
- It uses shuffled orders on ONE machine. It does not show that the 5070 Ti (NumPy 2.4.5) and the 1660 SUPER (NumPy 2.5.2) compute
  different coefficients; the decision does not need that, because shipping the coefficients removes the question.
- Rewards of other kinds (not k/96), other N, other values of eta were not tried.
- The 0.3 to 0.4% rate belongs to this family of rewards; do not quote it as a general constant.

## Files

`measure.py` (the script), `output.txt` (its output, as produced), `SHA256SUMS`.
