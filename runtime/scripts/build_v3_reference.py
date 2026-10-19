#!/usr/bin/env python3
"""Make the desktop-v3 qualification reference: the pinned adapter file, then both cells observed on this GPU.

    HETEROES_GPU_ACCEPTANCE=1 python scripts/build_v3_reference.py --gpu --model-path <Qwen snapshot> \\
        --model-id Qwen/Qwen2.5-0.5B-Instruct --revision 7ae557604adf67be50417f59c2c2f167def9a775 \\
        --adapter-seed 7 --out <new directory>

The adapter is made from its seed on Linux only (native Windows PyTorch gives other bytes for the same seed); pass
`--adapter <file>` to reuse a pinned one. `--cpu-fixture` builds on the CPU for tests: such a reference is not shipped.
The output directory must not exist; it receives reference-v3.json and the adapter file side by side.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--adapter", type=Path)
    source.add_argument("--adapter-seed", type=int)
    device = parser.add_mutually_exclusive_group(required=True)
    device.add_argument("--gpu", action="store_true")
    device.add_argument("--cpu-fixture", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.gpu and os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        raise ValueError("Set HETEROES_GPU_ACCEPTANCE=1 after owner authorization")
    if args.adapter_seed is not None and sys.platform == "win32":
        raise ValueError("Make adapters from a seed on Linux; pass --adapter with the pinned file")
    if args.out.exists():
        raise FileExistsError(args.out)
    from heteroes.product.qualification_v3 import ADAPTER_SPACE, build_reference, write_reference

    with tempfile.TemporaryDirectory(prefix="heteroes-v3-reference-") as temporary:
        adapter = args.adapter
        if adapter is None:
            from heteroes.model.lora import create_initial_adapter
            from heteroes.v3.model import file_manifest, load

            donor, _ = load(args.model_path, file_manifest(args.model_path), "cpu")
            adapter = Path(temporary) / "adapter.bin"
            create_initial_adapter(donor, ADAPTER_SPACE, args.adapter_seed, adapter)
            del donor
        device = "cuda" if args.gpu else "cpu"
        reference = build_reference(
            args.model_path, args.model_id, args.revision, adapter, device, emit=lambda event: print(event, flush=True)
        )
        path = write_reference(reference, adapter, args.out)
    print(f"wrote {path} (adapter {reference['adapter']['sha256']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
