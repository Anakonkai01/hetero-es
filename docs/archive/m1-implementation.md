# M1 implementation record

Date: 2026-10-10. Status: M1 implemented and verified locally; not released.

Accepted scope and future milestones: [lab-roadmap.md](lab-roadmap.md).

Branches:

- Product: `feat/lab-operations-product`, based on `7532750`.
- Runtime: `feat/lab-operations-control`, based on `51e1b2a`.

## Delivery sequence

1. Save the accepted roadmap and inspect current services and persisted state.
2. Copy the live product database and verify a versioned migration against it.
3. Implement account lifecycle, sessions, independent workspace membership and
   resource assignment with authorization regression tests.
4. Add runtime maintenance/snapshot support, idle backup/restore and operations.
5. Connect real frontend flows and retain explicit mock behavior.
6. Verify browser flows, previous integration behavior and safe live migration.
7. Record sanitized evidence, update runtime status and make local commits.

## Progress and evidence

- Roadmap and M1 requirements saved; both implementation branches created.
- Existing integration branches and clean baseline commits preserved.
- Schema migration verified on a separate live-database copy and then on the
  running deployment. Exact preserved-data SHA-256 over experiment rows, FIFO,
  sessions and existing password hashes:
  `efcc1b864abaf5819379940a7bac8c2420b803d607f8643d503add9064938490`.
- Backend contract checks: 45 passed. Track A full CPU suite: 2,143 passed,
  21 skipped. Frontend build/lint and 22 explicit mock behavior groups passed.
- Scratch mutations removing workspace isolation and the runtime maintenance
  submission guard were both caught.
- Track A control implementation committed locally as `2877877`; no push.
- Real browser registration, approval, workspace creation, invitation acceptance,
  owner isolation, contribution reassignment and session revocation passed. An
  actual 3060 run was cancelled cooperatively with a retained checkpoint; the
  GPU was returned to `lab` afterwards. Browser errors: none.
- Required two-GPU acceptance completed with both 5070 Ti and Quang's 3060:
  `096b09ec03ab4d8b9ca189596593db3a`, N=8/G=3, `arith16`, `hf_generate`,
  FP32 evaluation, CPU noise, alpha=sigma=0.001. Accepted results: 17 local,
  7 remote. Three generations published; both workers confirmed shutdown.
  Final downloaded checkpoint SHA-256:
  `987541249378460c668ff9865cbcc5823331eddae4bdfbebd87a532977b96c38`.
- Real idle backup and new-directory restore passed with a 33,597,880,320-byte
  bundle. All historical product tables, 16 experiments and 13 checkpoint
  references were preserved. Imported sessions were revoked, the queue remained
  held, and runtime credentials and process/worker directories were regenerated.
  Old process identity records were absent. Full round-trip time: 2,477.6 seconds.
- Cold boot of the restored deployment on separate ports passed: preserved
  password login, held queue, historical generations and actual checkpoint
  download through the restored backend and runtime. Its checkpoint checksum
  matched the original. No GPU jobs launched. Auxiliary services were then stopped;
  the original deployment remains the working deployment.
- Native browser backup download authorization passed without allocating the
  entire bundle in JavaScript; the acceptance download was cancelled immediately
  to avoid creating another 33 GB copy.
- Completed runtime transfer archives are retired after verification of the
  combined backup. Cleanup failure retains a valid bundle and is audited. Final
  regression tests cover that case and holding dispatch through the final checksum.
  These refinements were CPU-tested after the full-size restore campaign.
- Conservative cumulative GPU usage across 14 runtime runs: 0.605631 GPU-hours
  used from the original 2; 1.394369 remain. No reset.

Sanitized evidence: sibling Track A
`artifacts/experiments/2026-10-10-m1-lab-operations/`. Raw databases, screenshots,
credentials and full-size archives remain in private deployment directories,
outside Git. Prior integration and research evidence was preserved.

## Delivered behavior and remaining scope

M1 delivers persisted account permissions, workspace roles, contribution ownership,
queue visibility, operations/audit views and safe idle backup/restore. Operators
can use [lab-operations.md](lab-operations.md) for startup and recovery. The
deployment still uses static Linux/SSH worker configuration, manual startup and
one global active run. The optional 1660S remains unavailable and unvalidated.
Windows/Linux installers, GPU-independent control, public networking and parallel
scheduling belong to M2–M6 and have not been implemented by M1. No push, merge,
tag or public deployment was performed.
