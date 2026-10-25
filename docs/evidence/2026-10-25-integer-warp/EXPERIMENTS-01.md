# Interpretation of retained experiment receipts

All experiments start from selected97f62431, remain unselected and keep hardwareQualified=false.

- `unsupported-warps-red-01`: the selected source rejects1/2warps, as expected. First remote setup logs
  `decode-warps-*-01.log` fail before computation because the scratch archive had not been created; retained.
- `decode-warps-*-02.json`: successful sweeps,430 variants onNhut5070Ti and384 onQuang3060. Output bits equal
  the baseline in every variant, with sampled independent CPU checks. Uniform1/2warp auto-split policies regress
  geometric mean; see `warp-decision-01.json`. No new public warp policy is selected.
- `row-tiles-*-01.json`: successful B64/B128 sweeps,217/198 variants. Tile64 geometric mean ratio versus32 is
  .853/.949 onNhut/Quang; tile128 .621/.712. Tile128 spills; retain32. Events are not trained throughput.
- `bench-packing-shift-*-nhan-01.json` are **misnamed baseline controls**, not shift results: setup stopped before
  patching the copied source. Their integer source identity is unchanged97f62431. `bench-packing-prmt-smol-nhan-01`
  fails because that scratch module path was absent. Neither is evidence for candidate throughput.
- `bench-packing-{shift,prmt}-*-nhan-02.json` are the actual current-schedule candidates. Source identities record
  the modified module. Exact packing was exhaustively checked in the preceding conversion folder; promotion and
  current trained parent/candidate/restore checks remain separate. Three trained parent B32 gains are about6–9%.

## What this does NOT show

No selected code change, general quality/qualification, whole-plan completion or serving/end-to-end ES throughput.
No push/merge/deploy or learning. Failed/rejected attempts remain visible and are not rewritten as passing evidence.
