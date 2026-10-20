"""Frozen v3 run inputs and selection required beyond the numerical checkpoint."""

from pathlib import Path
import os

from heteroes.product.files import read_json, write_json
from heteroes.product.storage import data_root
from heteroes.recovery_manifest import HEX
from heteroes.v3.data import verify as verify_dataset
from heteroes.v3.run import RecipeV3Run


def validate_state(state, config, recipe, generation, files):
    if not isinstance(state, dict) or state.get("recipe") != recipe:
        raise ValueError("Recovery recipe mismatch")
    run = RecipeV3Run(recipe, state["plan"], allow_python=True)  # its code was pinned when the run was created
    dataset = verify_dataset(state["dataset"])
    identity = {k: dataset[k] for k in ("contentHash", "splitHashes")}
    if identity != config["datasetIdentity"] or identity != {k: recipe["data"][k] for k in identity}:
        raise ValueError("Recovery dataset mismatch")
    selection = state.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("Recovery requires validation selection")
    for row in [selection, *state["validation"]]:
        if row.get("recipeHash") != run.hash or row.get("planHash") != run.plan_hash:
            raise ValueError("Recovery validation recipe or plan mismatch")
        if type(row.get("generation")) is not int or not -1 <= row["generation"] <= generation:
            raise ValueError("Invalid validation generation")
    best = selection.get("weightsSha256")
    if not isinstance(best, str) or not HEX.fullmatch(best) or f"selection/{best}.bin" not in files:
        raise ValueError("Missing selected weights")
    if not any(
        row["generation"] == selection["generation"]
        and row["weightsSha256"] == best
        and row["meanReward"] == selection["validationReward"]
        for row in state["validation"]
    ):
        raise ValueError("Selection lacks validation history")
    generations = [row["generation"] for row in state["validation"]]
    if len(set(generations)) != len(generations) or -1 not in generations:
        raise ValueError("Incomplete validation history")
    space = recipe["weightSpace"]
    if space["kind"] == "lora" and files.get("initial-adapter.bin", {}).get("sha256") != space["initialAdapterSha256"]:
        raise ValueError("Missing pinned initial adapter")
    return run


def capture_state(root, temporary, recipe, generation):
    root, temporary = Path(root), Path(temporary)
    config = read_json(root / "config.json")
    state = {
        "recipe": read_json(root / "recipe.json"),
        "plan": read_json(root / "plan.json"),
        "dataset": read_json(config["datasetPath"]),
        "selection": read_json(root / "study-selection.json"),
        "validation": [read_json(p) for p in sorted(root.glob("validation-*.json"))],
        "auditFaults": read_json(root / "audit-faults.json", {}),
    }
    selection = state["selection"]
    if not selection:
        raise ValueError("Recovery requires validation selection")
    best = selection.get("weightsSha256")
    if not isinstance(best, str) or not HEX.fullmatch(best):
        raise ValueError("Invalid selected weights")
    paths = {f"selection/{best}.bin": data_root(root) / "selection" / f"{best}.bin"}
    if recipe["weightSpace"]["kind"] == "lora":
        paths["initial-adapter.bin"] = data_root(root) / "initial-adapter.bin"
    # Sources are immutable weights. Never carry process IDs, credentials or grants.
    for name, source in paths.items():
        if source.is_symlink() or source.parent.is_symlink() or not source.is_file():
            raise ValueError("Missing or unsafe selected weights / initial adapter")
        target = temporary / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.link(source, target)
    write_json(temporary / "v3-state.json", state)
    return ["v3-state.json", *paths]


def restore_state(point, temporary, destination):
    state = read_json(Path(point) / "v3-state.json")
    for name, value in (
        ("recipe.json", state["recipe"]),
        ("plan.json", state["plan"]),
        ("dataset.json", state["dataset"]),
        ("study-selection.json", state["selection"]),
        ("audit-faults.json", state["auditFaults"]),
    ):
        write_json(temporary / name, value)
    for row in state["validation"]:
        write_json(temporary / f"validation-{row['generation']}.json", row)
    config = read_json(temporary / "config.json")
    config["datasetPath"] = str(Path(destination).resolve() / "dataset.json")
    config["modelManifestPath"] = str(Path(destination).resolve() / "model-manifest.json")
    write_json(temporary / "model-manifest.json", config["modelManifest"])
    write_json(temporary / "config.json", config)
    # Export receipts refer to external export files; restore keeps the test locked.
    # Rebuild this projection from retained canonical history, never trust stale paths.
    selection = state["selection"]
    write_json(
        temporary / "study-metrics.json",
        {
            "recipeHash": selection["recipeHash"],
            "planHash": selection["planHash"],
            "datasetIdentity": config["datasetIdentity"],
            "metric": "mean-reward",
            "weightSpace": state["recipe"]["weightSpace"]["kind"],
            "scorer": state["plan"]["scorer"],
            "best": selection,
            "testLocked": True,
            "validation": sorted(
                ({k: row[k] for k in ("generation", "weightsSha256", "meanReward")} for row in state["validation"]),
                key=lambda row: row["generation"],
            ),
        },
    )
