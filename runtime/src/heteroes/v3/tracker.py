"""Coordinator validation and a locked test split for Recipe v3's frozen declarative scorer."""

import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from heteroes.canonical import canonical_json_hash
from heteroes.eval.precision import EvalModel
from heteroes.eval.candidate import model_weights_sha256
from heteroes.model.weights_io import load_weights_
from heteroes.product.files import read_json, write_json
from heteroes.product.storage import data_root
from heteroes.study.evaluation import generate_rows
from heteroes.v3.scoring import score


class Tracker:
    def __init__(
        self, root, loaded, recipe, dataset, interval=1, *, model_path=None, log=lambda event: None, python_scorer=None
    ):
        if type(interval) is not int or interval < 1:
            raise ValueError("validation interval must be a positive integer")
        self.root, self.loaded, self.recipe, self.dataset = Path(root), loaded, recipe, dataset
        self.interval, self.model_path, self.log = interval, model_path, log
        self.python_scorer = python_scorer  # the loaded code of a Python scorer spec (None for a declarative one)
        self.eval_model = EvalModel(loaded.model, recipe.eval_dtype)
        self.best = read_json(self.root / "study-selection.json")
        if self.best and (self.best.get("recipeHash") != recipe.hash or self.best.get("planHash") != recipe.plan_hash):
            raise ValueError("Validation selection belongs to another recipe or scoring plan")

    def _evaluate(self, model, tokenizer, split):
        rows = list(self.dataset["splits"][split])  # a file-backed split is read once, in order
        # the recipe's prompts per generate() call (16 when it fixes none, as the executor); texts are coordinator-only
        raw = generate_rows(model, tokenizer, rows, self.recipe.evaluation, self.recipe.chunk or 16)
        reward, scores = score(self.recipe.plan["scorer"], [r["output"] for r in raw], rows, self.python_scorer)
        return {
            "meanReward": reward,
            "scores": scores,
            "rows": raw,
            "count": len(rows),
            "split": split,
            "rowsHash": canonical_json_hash(rows),
            "scorer": self.recipe.plan["scorer"],
        }

    def _metrics(self, *, receipt=None):
        history = [
            {key: row[key] for key in ("generation", "weightsSha256", "meanReward")}
            for path in sorted(self.root.glob("validation-*.json"))
            if (row := read_json(path))
        ]
        write_json(
            self.root / "study-metrics.json",
            {
                "recipeHash": self.recipe.hash,
                "planHash": self.recipe.plan_hash,
                "datasetIdentity": {k: self.dataset[k] for k in ("contentHash", "splitHashes")},
                "metric": "mean-reward",
                "weightSpace": self.recipe.recipe["weightSpace"]["kind"],
                "scorer": self.recipe.plan["scorer"],
                "best": self.best,
                "validation": sorted(history, key=lambda item: item["generation"]),
                "testLocked": receipt is None,
                **({"testReward": receipt["test"]["meanReward"], "independentReloadPassed": True} if receipt else {}),
            },
        )

    def observe(self, generation, weights_sha):
        if generation >= 0 and (generation + 1) % self.interval and generation + 1 != self.recipe.plan["generations"]:
            return
        self.eval_model.refresh()
        result = self._evaluate(self.eval_model.model, self.loaded.tokenizer, "validation")
        result.update(
            generation=generation,
            weightsSha256=weights_sha,
            recipeHash=self.recipe.hash,
            planHash=self.recipe.plan_hash,
        )
        write_json(self.root / f"validation-{generation}.json", result)
        if self.best is None or result["meanReward"] > self.best["validationReward"]:
            selection = {
                "generation": generation,
                "weightsSha256": weights_sha,
                "validationReward": result["meanReward"],
                "recipeHash": self.recipe.hash,
                "planHash": self.recipe.plan_hash,
            }
            directory = data_root(self.root) / "selection"
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = directory / f"{weights_sha}.bin"
            if not target.exists():
                os.link(data_root(self.root) / "weights" / f"{weights_sha}.bin", target)
            write_json(self.root / "study-selection.json", selection)
            previous, self.best = self.best, selection
            if previous and previous["weightsSha256"] != weights_sha:
                (directory / f"{previous['weightsSha256']}.bin").unlink(missing_ok=True)
        self._metrics()
        self.log(
            {
                "event": "validation_completed",
                "generation": generation,
                "meanReward": result["meanReward"],
                "weightsSha256": weights_sha,
            }
        )

    def _release_device(self):
        """
        D1 (ADR-013): the export reload below must be the only weight set on this GPU. The run is over and the selected
        weights were tested above, so the live model (and an FP32 shadow, and its strict engine) moves to the CPU; the
        files and the LoRA export are written from there, and nothing evaluates the live model afterwards.
        """
        if next(self.loaded.model.parameters()).device.type != "cuda":
            return
        import torch

        from heteroes.eval import strict_backend

        strict_backend.release(self.loaded.model)
        self.loaded.model.to("cpu")
        if self.eval_model.model is not self.loaded.model:
            self.eval_model.model.to("cpu")
        torch.cuda.empty_cache()

    def export(self):
        if self.best is None:
            raise ValueError("No validated checkpoint selected")
        destination = data_root(self.root) / "export"
        receipt = read_json(self.root / "study-export.json")
        if receipt:
            if (
                receipt.get("planHash") != self.recipe.plan_hash
                or receipt.get("weightsSha256") != self.best["weightsSha256"]
            ):
                raise ValueError("Export receipt lineage mismatch")
            for name, digest in receipt["exportFiles"].items():
                with (destination / name).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                        raise ValueError("Export file checksum mismatch")
            self._metrics(receipt=receipt)
            return receipt
        if destination.exists():
            raise ValueError("Unverified export directory already exists")
        if "frozenBaseSha256" in self.recipe.recipe["weightSpace"]:
            raise ValueError("Export of a frozen int8 base with its adapters is not built (M6)")
        selected = data_root(self.root) / "selection" / f"{self.best['weightsSha256']}.bin"
        load_weights_(self.loaded.model, self.loaded.schema, selected, self.best["weightsSha256"])
        self.eval_model.refresh()
        test = self._evaluate(self.eval_model.model, self.loaded.tokenizer, "test")
        self._release_device()
        stage = Path(tempfile.mkdtemp(prefix=".v3-export-", dir=data_root(self.root)))
        try:
            from heteroes.v3.model import file_manifest, load, trainable_schema

            space = self.recipe.recipe["weightSpace"]
            if space["kind"] == "lora":
                import torch
                from peft import PeftModel
                from heteroes.model.lora import export_peft, trainable_schema as adapter_schema

                if self.model_path is None:
                    raise ValueError("LoRA export needs its pinned base model path")
                export_peft(
                    self.loaded.model,
                    space,
                    stage,
                    self.recipe.recipe["model"]["id"],
                    self.recipe.recipe["model"]["revision"],
                )
                base, tokenizer = load(self.model_path, self.recipe.recipe["model"]["files"], self.loaded.device)
                reloaded = PeftModel.from_pretrained(base, stage).to(dtype=torch.float16).get_base_model()
                schema = adapter_schema(reloaded)
            else:
                self.loaded.model.save_pretrained(stage, safe_serialization=True)
                self.loaded.tokenizer.save_pretrained(stage)
                reloaded, tokenizer = load(stage, file_manifest(stage), self.loaded.device)
                schema = trainable_schema(reloaded, space)
            actual = model_weights_sha256(reloaded, schema)
            if actual != self.best["weightsSha256"]:
                raise ValueError("Export reload canonical weights mismatch")
            repeated_eval = EvalModel(reloaded, self.recipe.eval_dtype)
            repeated_eval.refresh()
            repeated = self._evaluate(repeated_eval.model, tokenizer, "test")
            if repeated != test:
                raise ValueError("Export reload predictions or scores mismatch")
            files = {}
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    with path.open("rb") as stream:
                        files[path.relative_to(stage).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
            receipt = {
                "formatVersion": 2,
                "recipeHash": self.recipe.hash,
                "planHash": self.recipe.plan_hash,
                "weightsSha256": actual,
                "weightSpace": space,
                "selection": self.best,
                "test": test,
                "independentReloadPassed": True,
                "exportFiles": files,
            }
            write_json(stage / "heteroes-export.json", receipt)
            from heteroes.product.recovery import publish_new_directory

            publish_new_directory(stage, destination)
            write_json(self.root / "study-export.json", receipt)
            self._metrics(receipt=receipt)
            return receipt
        finally:
            if stage.exists():
                shutil.rmtree(stage)
