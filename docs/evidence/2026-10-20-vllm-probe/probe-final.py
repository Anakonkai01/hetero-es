"""Owner-authorized vLLM feasibility probe; never a runtime decoder implementation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time


def fingerprint(model):
    import torch
    torch.backends.cuda.matmul.allow_tf32 = False
    digest = hashlib.sha256()
    for name, tensor in sorted(model.named_parameters()):
        digest.update(name.encode() + b"\0")
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--hf-only", action="store_true")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.gpu or os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        raise ValueError("The probe needs --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if args.out.exists():
        raise FileExistsError(args.out)
    args.artifacts.mkdir(parents=True, exist_ok=False)
    result = {"phase": "imports", "acceptedAsRuntimeDecoder": False}

    def phase(name):
        result["phase"] = name
        print(json.dumps({"phase": name}), flush=True)

    try:
        import torch
        from safetensors.torch import save_file
        from heteroes.es.perturb import perturb_model_
        from heteroes.es.snapshot import take_snapshot, restore_from_snapshot_
        from heteroes.eval.candidate import model_weights_sha256
        from heteroes.eval.precision import EvalModel
        from heteroes.model.loading import check_noise_selftest
        from heteroes.runtime_info import environment_info
        from heteroes.study.evaluation import generate_rows
        from heteroes.v3.model import file_manifest, load, trainable_schema

        torch.backends.cuda.matmul.allow_tf32 = False
        check_noise_selftest()
        result["environment"] = environment_info("cuda")
        rows = [{"prompt": f"Compute {17 + i} * {23 + 2*i}. " +
                 ("Show the calculation step by step, then give the integer answer." if i % 4 == 0 else
                  "Reply with only the integer.")} for i in range(64)]
        result["rows"] = rows
        evaluation = {"systemPrompt": None, "maxNewTokens": 64, "decoder": "hf_generate"}
        files = file_manifest(args.model)
        model, tokenizer = load(args.model, files, "cuda")
        schema = trainable_schema(model, {"kind": "full"})
        generation_config = model.generation_config.to_dict()
        result["generationConfig"] = generation_config
        parent = model_weights_sha256(model, schema)
        snapshot = take_snapshot(model, schema)
        evaluator = EvalModel(model, "float32")
        hf = {}
        for cell in ("base", "perturbed"):
            phase("hf_" + cell)
            if cell == "perturbed":
                perturb_model_(model, schema, 20261020, 0.01)
                save_file({name: tensor.detach().cpu().contiguous() for name, tensor in model.named_parameters()}, str(args.artifacts / "perturbed.safetensors"))
                result["perturbedSha256"] = model_weights_sha256(model, schema)
            evaluator.refresh()
            raw = generate_rows(evaluator.model, tokenizer, rows, evaluation, 64)
            outputs = [row["output"] for row in raw]
            seconds = []
            for _ in range(3):
                torch.cuda.synchronize()
                started = time.perf_counter()
                repeated = generate_rows(evaluator.model, tokenizer, rows, evaluation, 64)
                torch.cuda.synchronize()
                seconds.append(time.perf_counter() - started)
                assert [row["output"] for row in repeated] == outputs
            hf[cell] = {"outputs": outputs, "seconds": seconds, "medianSeconds": statistics.median(seconds)}
        restore_from_snapshot_(model, schema, snapshot)
        assert model_weights_sha256(model, schema) == parent
        result.update(parentSha256=parent, hf=hf, hfRestoreExact=True, evaluation=evaluation)
        if args.hf_only:
            phase("complete")
            return 0
        # Release the HF models before the vLLM worker reserves its KV cache.
        import gc
        del evaluator, model, snapshot
        gc.collect()
        torch.cuda.empty_cache()
        phase("vllm_initialization")
        from vllm import LLM, SamplingParams
        import vllm

        result["vllmVersion"] = vllm.__version__
        started = time.perf_counter()
        llm = LLM(model=str(args.model), tokenizer=str(args.model), dtype="float32", trust_remote_code=False,
                  tensor_parallel_size=1, max_model_len=512, max_num_seqs=64, max_num_batched_tokens=8192,
                  gpu_memory_utilization=0.45, enforce_eager=True, enable_prefix_caching=False,
                  attention_config={"backend": "FLEX_ATTENTION"}, seed=11)
        result["initializationSeconds"] = time.perf_counter() - started
        initial = llm.apply_model(fingerprint)
        prompts = [tokenizer.apply_chat_template([{"role": "user", "content": row["prompt"]}],
                                                tokenize=False, add_generation_prompt=True) for row in rows]
        params = SamplingParams(temperature=0, max_tokens=64, seed=11,
                                repetition_penalty=generation_config.get("repetition_penalty", 1.0),
                                stop_token_ids=generation_config.get("eos_token_id"))
        vllm_cells = {}
        result["vllm"] = vllm_cells
        for cell in ("base", "perturbed", "restored"):
            phase("vllm_" + cell)
            reload_seconds = 0
            if cell != "base":
                path = str(args.artifacts / "perturbed.safetensors") if cell == "perturbed" else str(args.model / "model.safetensors")
                def reload(model, path=path):
                    import torch
                    from safetensors.torch import load_file
                    weights = load_file(path, device="cpu")
                    loaded = model.load_weights(weights.items())
                    checked = 0
                    mismatches = []
                    for name, tensor in model.named_parameters():
                        if '.qkv_proj.' in name:
                            source = torch.cat([weights[name.replace('.qkv_proj.', '.'+part+'_proj.')] for part in ('q','k','v')],dim=0)
                        elif '.gate_up_proj.' in name:
                            source = torch.cat([weights[name.replace('.gate_up_proj.', '.'+part+'_proj.')] for part in ('gate','up')],dim=0)
                        else:
                            source = weights['model.embed_tokens.weight' if name == 'lm_head.weight' and name not in weights else name]
                        if not torch.equal(tensor.detach().cpu(), source.to(tensor.dtype)):
                            mismatches.append(name)
                        checked += 1
                    torch.cuda.synchronize()
                    assert not mismatches, 'Reloaded parameters differ from HF source: '+str(mismatches[:5])
                    return {"loadedTensors":len(loaded),"verifiedTensors":checked}
                started = time.perf_counter()
                loaded = llm.apply_model(reload)
                reload_seconds = time.perf_counter() - started
                result[cell + "LoadedTensors"] = loaded
            observed = llm.apply_model(fingerprint)
            if cell == "restored":
                assert observed == initial, "vLLM parameter bytes did not restore exactly"
            generated = llm.generate(prompts, params, use_tqdm=False)
            outputs = [row.outputs[0].text for row in generated]
            seconds = []
            for _ in range(3):
                started = time.perf_counter()
                repeated = llm.generate(prompts, params, use_tqdm=False)
                seconds.append(time.perf_counter() - started)
                assert [row.outputs[0].text for row in repeated] == outputs
            expected = hf["base" if cell == "restored" else cell]
            vllm_cells[cell] = {"outputs": outputs, "seconds": seconds,
                               "medianSeconds": statistics.median(seconds), "reloadSeconds": reload_seconds,
                               "parameterFingerprint": observed,
                               "differentTextsFromHF": sum(a != b for a, b in zip(outputs, expected["outputs"], strict=True)),
                               "outputTokens": sum(len(row.outputs[0].token_ids) for row in generated)}
        result["vllm"] = vllm_cells
        result["vllmRestoreExact"] = True
        result["vllmRestoredTextsEqualBase"] = vllm_cells["restored"]["outputs"] == vllm_cells["base"]["outputs"]
        phase("complete")
        return 0
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)[:3000]}
        print(json.dumps({"failedPhase": result["phase"], **result["error"]}), flush=True)
        return 1
    finally:
        with args.out.open("x") as stream:
            json.dump(result, stream, indent=1)
            stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
