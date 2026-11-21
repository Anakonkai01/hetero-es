# Third-party sources and dependency pins

This inventory was checked on 2026-11-21. It records the model and dataset used by the researcher example, the
configuration for distributed packages and the selected references used in HeteroES. The project's own license is
in [LICENSE](../LICENSE).

## Model and data

| Upstream origin | Pinned revision | Use in HeteroES |
| --- | --- | --- |
| [Qwen/Qwen2.5-0.5B-Instruct model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/7ae557604adf67be50417f59c2c2f167def9a775/README.md) (Apache-2.0) | `7ae557604adf67be50417f59c2c2f167def9a775` | Recipe v1 model and tokenizer, and the model used by the researcher example. [Canonical model pin](src/heteroes/catalog.py). |
| [openai/gsm8k dataset card](https://huggingface.co/datasets/openai/gsm8k/blob/740312add88f781978c0658806c59bc2815b9866/README.md) (MIT) | `740312add88f781978c0658806c59bc2815b9866` | Main split used by the researcher example and dataset preparation script. The builder verifies the input Parquet hashes. [Dataset builder](scripts/build_gsm8k_dataset.py). |

The [strict parity fixture](../acceptance/golden/strict-b22.json) records file hashes for Qwen, Smol and Tiny.
Consult the model manifest of a specific experiment for asset provenance. An experiment's model revision and file hashes
belong to that experiment's record.

## Software packages

| Area | Source of truth |
| --- | --- |
| Runtime Python and optional test/LoRA extras | [runtime/pyproject.toml](pyproject.toml) |
| Worker private Python environments | [Linux lock](../desktop/worker/resources/requirements-linux.txt) and [Windows lock](../desktop/worker/resources/requirements-windows.txt) |
| Desktop Server private Python environments | [Linux lock](../desktop/server/resources/requirements-linux.txt) and [Windows lock](../desktop/server/resources/requirements-windows.txt) |
| Backend packages | [CPU lock](../backend/requirements.lock.txt) and [cloud lock](../backend/requirements-cloud.lock.txt) |
| Web and Electron packages | [npm lockfile](../package-lock.json) and workspace package manifests |
| Packaged Worker font | [Font license](../desktop/worker/resources/FONT-LICENSE.txt) |

Both checked-in Worker locks pin PyTorch `2.13.0+cu132`, NumPy `2.5.3`, Transformers `5.17.0`,
PEFT `0.21.2`, Safetensors `0.8.0`, Tokenizers `0.23.2` and Hugging Face Hub `1.33.0`. The last published
installers have their own build and version record in [HANDOFF](../docs/HANDOFF.md).

## Research and provenance records

The October draft records papers consulted during the original work and questions about authorship and source
reuse that need project-owner confirmation. Individual packages and model assets carry their own upstream notices.
[October provenance draft](https://github.com/Anakonkai01/hetero-es/blob/8f5dc4f5/runtime/THIRD_PARTY.md) ·
[Historical methods and evidence](../docs/EVIDENCE-INDEX.md).
