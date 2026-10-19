# Managed Recipe v3 experiments

The staged product path uses the same recipe/plan builder and training runtime as the local v3 CLI/SDK. It has not been deployed to the live lab. The shared lab accepts declarative scorers only; Python rewards remain a self-hosted SDK/CLI feature.

In **Models**, select **Custom experiment · Recipe v3** under **Asset recipe**. Import JSON, JSONL or CSV, map the prompt column and keep the remaining scalar columns for scoring. A single file uses the seeded 80/10/10 split; three named files keep explicit splits. Duplicate prompts across or within splits are rejected. Imports are limited to 3 MB per file and 10 MB per frozen document.

Register a pinned safetensors model manifest with Recipe v3 selected. It has the existing manifest structure: `formatVersion: 1`, `modelId`, exact 40-hex `revision` and `tokenizerRevision`, `format: "safetensors"`, and `files` mapping safe relative file names to SHA-256. V3 permits any causal LM supported locally by Transformers without remote code. Choose a pinned reference or upload every declared file. V2 retains its existing model-family policy.

In **Create experiment**, select **Custom experiment · Recipe v3**, then the model, dataset, batch and sigma settings. Choose full parameters, subset patterns or LoRA rank/alpha/target modules. Antithetic sampling is off by default and requires an even population when enabled. The implemented coefficient rule is `zscore@1`.

Choose a declarative scorer and its dataset column/configuration. Exact-string, choice-letter and regex scorers can use arbitrary answer-column names; the three numeric compatibility scorers read `answer`. A system prompt can be absent (`null`) or explicitly supplied. Validation uses this same frozen scorer at the chosen interval. Select qualified devices, review and save a draft; submitting freezes the configuration.

Devices must advertise `[3]`, repeated numerical compatibility evidence and qualification for the model's manifest hash. The r11 qualification/profile work and real Windows/GPU acceptance are still pending; a device's network connection is not qualification. Do not manufacture compatibility evidence or use the browser fixture declarations on real devices.

Workers verify model files, the dataset identity, trainable schema and generation configuration before admission. LoRA workers fetch the pinned initial adapter through the authenticated private weights route; public replay-only workers need that adapter in their verified cache already. The coordinator retains the initial adapter even when older generation weights are pruned.

Validation rewards, generation history and the selected checkpoint appear in metrics and the product timeline. Higher validation reward wins; ties preserve the earlier checkpoint. Test stays locked until workers stop and final export reloads the selected full/subset safetensors or PEFT adapter, verifies its trainable-weight hash and repeats test outputs and scores. A failed export leaves an error receipt and test locked. Runs with different weight spaces do not share reward chart axes.

These CPU fixture checks establish integration and selection/export behavior, not real-model learning, hardware compatibility, disaster recovery, installer readiness or live deployment. The existing recovery-point format does not include the v3 recipe/plan, initial adapter and validation selection history; complete v3 disaster recovery must be addressed and qualified before the flag day. In-place process restart/pause retains these files and is a different case.
