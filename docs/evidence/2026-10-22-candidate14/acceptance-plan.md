# Candidate14 live acceptance (declared before submission)

Use the published researcher SDK with the existing session, reference Qwen 0.5B
model, and the twenty public multiplication rows from the qualification. Submit
through `ESTrainer.submit`, with the nhan coordinator and all three currently
approved, ON, idle V2 workers: nhan, nhut, and native Windows Thao. Do not change
approvals or wake the two offline machines.

Run ten generations of eight antithetic candidates, batch four, FP32 evaluation,
full weights, sigma/alpha 0.001, `hf_generate`, 32 new tokens, exact chunk 16,
`zscore@1`, and declarative `last-integer`. This is system acceptance, not a
learning experiment. Keep nhut's existing public-only firewall rule throughout.

Before queueing, record the draft ID, input hashes, saved engine, identities,
and the default deterministic 5% audit selection. Require at least one selected
audit. A draft with no selected audit may be left unsubmitted and documented;
there is no reward-based selection and no change to the production audit rate.

Accept only if all ten updates and eighty candidates complete, all three
workers contribute, at least one update is nonzero, selected audits finish
without mismatches, and independent ledger replay matches all ten child hashes
on both Linux hosts. Record native installed-runtime parity separately. Check
process release, current telemetry, and the live/replay UI. Preserve failures
and their limits. Then remove only the exact temporary nhut firewall rule and
diagnostic directories, close the Windows debug launch, and push/FF main.
