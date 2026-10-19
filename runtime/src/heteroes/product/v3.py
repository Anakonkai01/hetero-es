"""Adapt frozen product settings to the same Recipe v3 documents as the local SDK."""

import hashlib
from pathlib import Path

from heteroes.product.files import read_json, write_json
from heteroes.v3.scoring import validate_spec


def prepare_run(config, root, device, *, declared=None, client=None, cache=None):
    """Load verified inputs; on workers rebuild the declared recipe independently.

    The initial LoRA file is created once by the coordinator, then transferred by
    the existing authenticated private weights transport, with its content hash.
    """
    from heteroes.v3.options import validate_options

    validate_options(config)
    from heteroes.manifest import generation_config_sha256
    from heteroes.model.loading import LoadedModel
    from heteroes.model.lora import create_initial_adapter
    from heteroes.model.weights_io import publish_weights
    from heteroes.product.storage import data_root
    from heteroes.v3.data import verify
    from heteroes.v3.model import load, trainable_schema
    from heteroes.v3.run import RecipeV3Run, build_documents

    root = Path(root)
    dataset = verify(read_json(Path(config["datasetPath"])))
    if {k: dataset[k] for k in ("contentHash", "splitHashes")} != config["datasetIdentity"]:
        raise ValueError("Frozen dataset identity mismatch")
    manifest = config["modelManifest"]
    model, tokenizer = load(config["modelPath"], manifest["files"], device)
    space = dict(config["weightSpace"])
    adapter_sha = None
    if space["kind"] == "lora":
        if declared is not None:
            from heteroes.worker_runtime import download_weights

            adapter_sha = declared["weightSpace"]["initialAdapterSha256"]
            adapter = download_weights(client, adapter_sha, cache)
            space["initialAdapterSha256"] = adapter_sha
            schema = trainable_schema(model, space, adapter)
        else:
            adapter = data_root(root) / "initial-adapter.bin"
            previous = read_json(root / "recipe.json")
            if previous is not None:
                adapter_sha = previous["weightSpace"]["initialAdapterSha256"]
                space["initialAdapterSha256"] = adapter_sha
                schema = trainable_schema(model, space, adapter)
            else:
                if adapter.exists():
                    # A crash before recipe publication must not silently choose another initialization.
                    with adapter.open("rb") as stream:
                        adapter_sha = hashlib.file_digest(stream, "sha256").hexdigest()
                    space["initialAdapterSha256"] = adapter_sha
                    schema = trainable_schema(model, space, adapter)
                else:
                    adapter_sha = create_initial_adapter(model, space, 0, adapter)
                    from heteroes.model.lora import trainable_schema as adapter_schema

                    schema = adapter_schema(model)
            if publish_weights(model, schema, data_root(root) / "weights") != adapter_sha:
                raise ValueError("Published initial adapter hash mismatch")
    else:
        schema = trainable_schema(model, space)
    recipe, plan = build_documents(
        {
            "model": {"id": manifest["modelId"]},
            "weightSpace": space,
            "sigma": {"kind": config["sigmaSchedule"], "initial": config["sigma"], "minimum": config["sigmaMinimum"]},
            "generations": config["maxGenerations"],
            "population": config["candidatesPerGeneration"],
            "alpha": config["alpha"],
            "antithetic": config["antithetic"],
            "coefficientRule": config["coefficientRule"],
            "scorerSpec": config["scorer"],
            "systemPrompt": config["systemPrompt"],
            "batchSize": config["batchSize"],
            "batchSeed": config["batchSeed"],
            "maxNewTokens": config["maxNewTokens"],
            "decoder": config["decodeEngine"],
        },
        model_files=manifest["files"],
        revision=manifest["revision"],
        schema_hash=schema.hash,
        generation_config_sha256=generation_config_sha256(model.generation_config.to_dict()),
        dataset=dataset,
        adapter_sha256=adapter_sha,
    )
    run = RecipeV3Run(recipe, plan, allow_python=False)
    if declared is not None:
        if recipe != declared:
            raise ValueError("Local model/data/decoder differs from declared Recipe v3")
    else:
        for name, value in (("recipe.json", recipe), ("plan.json", plan)):
            previous = read_json(root / name)
            if previous is not None and previous != value:
                raise ValueError("Frozen Recipe v3 run documents changed")
            write_json(root / name, value)
    loaded = LoadedModel(
        model, tokenizer, schema, manifest["revision"], model.generation_config.to_dict(), device, manifest["modelId"]
    )
    return loaded, run, dataset
