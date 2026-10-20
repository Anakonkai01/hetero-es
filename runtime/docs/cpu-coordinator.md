# CPU-only coordinator (staged r11)

A machine without an NVIDIA GPU can coordinate Recipe v3 experiments through the Linux CLI. Install the isolated CLI
runtime as usual, then select the CPU admission test explicitly:

```bash
heteroes-worker selftest --device cpu
heteroes-worker join https://your-lab.example --coordinator --host <reachable-private-IP>
heteroes-worker run
```

The join command reads the pairing code from the terminal without echoing it. An administrator must approve the device
into the workspace. Turn contribution ON for the current boot, choose it as the experiment's coordinator, and select
qualified GPU workers separately. The default CUDA self-test and GPU worker flow remain available.

The CPU self-test verifies canonical noise and repeats a fixed update of 200,003 FP16 elements with three seeds against
an independent NumPy known answer. It advertises `runtimeProfile: coordinator-cpu-v3`, no GPU UUID, no qualified model
hashes and zero VRAM. It does not generate reference texts. Consequently it is excluded from worker selection and model
qualification probes. The lab reserves its device identity until confirmed process death; physical GPU reservations
belong only to GPU devices. CPU reservations do not count as legacy GPU reservations with missing UUIDs.

The agent writes `device: cpu` into its private configuration, passes `--device cpu` to the managed runner and hides CUDA
from that subprocess. A CPU profile refuses worker starts locally as well. The coordinator still loads the pinned model,
scores the workers' texts, applies recorded updates, validates checkpoints and exports the selected result. It needs
enough RAM and may validate much more slowly than a GPU. Validation texts are recorded; the update admission test makes
no claim that CPU validation texts match those of a GPU.

The synthetic update does not estimate full-model update speed, so `updateSecondsPerSeed` is absent/null for this profile.
Native Windows CPU admission uses the same profile validation, but this guide's installed CLI is Linux-only. Real native
Windows CPU acceptance requires its own receipt. This staged feature is not deployed to the public r10 lab.
