"""Validation selects a checkpoint; test stays locked until final export."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from heteroes.product.files import read_json, write_json
from heteroes.product.storage import data_root
from heteroes.eval.precision import EvalModel
from heteroes.eval.candidate import model_weights_sha256
from heteroes.model.weights_io import load_weights_
from .evaluation import evaluate, generate_rows, sampled_metrics
from .data import sha


class Tracker:
    def __init__(self, root, loaded, recipe, dataset, interval=1):
        self.root = Path(root)
        self.loaded = loaded
        self.recipe = recipe
        self.dataset = dataset
        self.interval = interval
        self.eval_model = EvalModel(loaded.model, "float32")
        self.best = read_json(self.root / "study-selection.json")
        if self.best and self.best["recipeHash"] != recipe.hash:
            raise ValueError("Validation selection belongs to another recipe")

    def observe(self, generation, weights_sha):
        if (
            generation >= 0
            and (generation + 1) % self.interval
            and generation + 1 != self.recipe.schedule["generations"]
        ):
            return
        self.eval_model.refresh()
        result = evaluate(
            self.eval_model.model, self.loaded.tokenizer, self.dataset["splits"]["validation"], self.recipe.evaluation
        )
        result.update(generation=generation, weightsSha256=weights_sha, recipeHash=self.recipe.hash, split="validation")
        write_json(self.root / f"validation-{generation}.json", result)
        # Ties keep the earlier checkpoint. Test has no role in this decision.
        if self.best is None or result["accuracy"] > self.best["validationAccuracy"]:
            selection = {
                "generation": generation,
                "weightsSha256": weights_sha,
                "validationAccuracy": result["accuracy"],
                "recipeHash": self.recipe.hash,
            }
            directory = data_root(self.root) / "selection"
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = data_root(self.root) / "weights" / f"{weights_sha}.bin"
            target = directory / f"{weights_sha}.bin"
            if not target.exists():
                os.link(source, target)
            write_json(self.root / "study-selection.json", selection)
            previous = self.best
            self.best = selection
            if previous and previous["weightsSha256"] != weights_sha:
                (directory / f"{previous['weightsSha256']}.bin").unlink(missing_ok=True)
        summary = {
            "recipeHash": self.recipe.hash,
            "datasetIdentity": self.recipe.dataset_identity,
            "best": self.best,
            "testLocked": True,
        }
        write_json(self.root / "study-metrics.json", summary)

    def export(self, samples=0):
        if not self.best:
            raise ValueError("No validated checkpoint selected")
        destination = data_root(self.root) / "export"
        receipt = read_json(self.root / "study-export.json")
        if receipt:
            if (
                receipt.get("recipeHash") != self.recipe.hash
                or receipt.get("weightsSha256") != self.best["weightsSha256"]
            ):
                raise ValueError("Export receipt lineage mismatch")
            for name, digest in receipt["exportFiles"].items():
                with (destination / name).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                        raise ValueError("Export file checksum mismatch")
            return receipt
        if destination.exists():
            raise ValueError("Unverified export directory already exists")
        selected = data_root(self.root) / "selection" / f"{self.best['weightsSha256']}.bin"
        load_weights_(self.loaded.model, self.loaded.schema, selected, self.best["weightsSha256"])
        self.eval_model.refresh()
        test = evaluate(
            self.eval_model.model, self.loaded.tokenizer, self.dataset["splits"]["test"], self.recipe.evaluation
        )
        test.update(split="test", selectionRule="highest validation accuracy; earliest on tie")
        sampled = None
        if samples:
            if samples != 32:
                raise ValueError("The frozen sampled protocol uses M=32")
            rows = []
            for index, row in enumerate(self.dataset["splits"]["test"]):
                raw = generate_rows(
                    self.eval_model.model,
                    self.loaded.tokenizer,
                    [row] * 32,
                    self.recipe.evaluation,
                    chunk=16,
                    sample=True,
                    seed=11 + index * 32,
                    temperature=0.6,
                )
                rows.append(
                    {
                        "prompt": row["prompt"],
                        "expected": row["answer"],
                        "raw": raw,
                        **sampled_metrics([r["prediction"] for r in raw], row["answer"]),
                    }
                )
            sampled = {
                "M": 32,
                "temperature": 0.6,
                "seed": 11,
                "K": [1, 16, 32],
                "rows": rows,
                "majorityTieBreak": "lexicographic",
            }
        stage = Path(tempfile.mkdtemp(prefix=".export-", dir=data_root(self.root)))
        try:
            self.loaded.model.save_pretrained(stage, safe_serialization=True)
            self.loaded.tokenizer.save_pretrained(stage)
            # Independently reload using Transformers, then rebuild the schema
            # and FP32 evaluation copy. No reuse of the in-memory source tensors.
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from heteroes.model.schema import build_parameter_schema

            reloaded = AutoModelForCausalLM.from_pretrained(
                stage, dtype=torch.float16, local_files_only=True, trust_remote_code=False, use_safetensors=True
            ).to(self.loaded.device)
            tokenizer = AutoTokenizer.from_pretrained(stage, local_files_only=True, trust_remote_code=False)
            actual = model_weights_sha256(reloaded, build_parameter_schema(reloaded))
            if actual != self.best["weightsSha256"]:
                raise ValueError("Export reload canonical weights mismatch")
            reload_eval = EvalModel(reloaded, "float32")
            reload_eval.refresh()
            repeated = evaluate(reload_eval.model, tokenizer, self.dataset["splits"]["test"], self.recipe.evaluation)
            if repeated["rows"] != test["rows"]:
                raise ValueError("Export reload predictions mismatch")
            del reload_eval, reloaded
            files = {}
            for path in stage.rglob("*"):
                if path.is_file():
                    with path.open("rb") as stream:
                        files[path.relative_to(stage).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
            receipt = {
                "formatVersion": 1,
                "recipeHash": self.recipe.hash,
                "weightsSha256": actual,
                "selection": self.best,
                "test": test,
                "sampled": sampled,
                "independentReloadPassed": True,
                "exportFiles": files,
                "exportDirectory": str(destination),
            }
            write_json(stage / "heteroes-export.json", receipt)
            from heteroes.product.recovery import publish_new_directory

            publish_new_directory(stage, destination)
            write_json(self.root / "study-export.json", receipt)
            write_json(
                self.root / "study-metrics.json",
                {
                    "recipeHash": self.recipe.hash,
                    "datasetIdentity": self.recipe.dataset_identity,
                    "best": self.best,
                    "testLocked": False,
                    "testAccuracy": test["accuracy"],
                    "independentReloadPassed": True,
                    "sampledProtocol": None if sampled is None else {"M": 32, "temperature": 0.6, "K": [1, 16, 32]},
                },
            )
            return receipt
        finally:
            if stage.exists():
                shutil.rmtree(stage)
