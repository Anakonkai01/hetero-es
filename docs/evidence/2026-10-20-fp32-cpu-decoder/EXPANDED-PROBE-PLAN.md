# Final-source hardware probe after reference lifetime fix

The first two-per-device implementation probe exposed no token disagreement. A subsequently added
reference-lifetime test caught a bound-method cycle that could retain a multi-GB CPU model until GC.
The final implementation uses a weak method and explicit signature; the lifetime regression passes,
and all 12 scratch mutations are killed. The first combined check was already running when this
small lifetime fix landed, so a fresh `final-checks/` combined gate is required for the final source.

After that gate, validate the final decoder source (record SHA256) on both GPUs with all eight original
generation-10 candidate seed/sign/index values, then repeat c5. Extract only those three public identity
fields from the preserved read-only ledger; never export leases. Use the same verified cached parent,
new decoder-bound recipe identity and original batch. Require all nine full token/text arrays and
primary perturbed/evaluation weight hashes to agree across devices, exact parent restore each time,
and the c5 hash to equal the original 5070 hash. Record reference calls and post-candidate available RAM.
This expansion exercises reference lifetime across successive candidates; it does not replace the
fresh packaged/Windows/50-generation gates or establish a universal arithmetic error bound.
