import argparse, json, os, sys, time
import numpy as np, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.es.update import apply_es_update_
from heteroes.eval.generate import generate_answer
from heteroes.eval.workload import exact_match_reward, extract_integer
from heteroes.manifest import derive_seed
from heteroes.model.schema import build_parameter_schema
import dataset

SNAP = os.path.expanduser("~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775")


def evaluate(model, tok, examples):
    return [int(exact_match_reward(extract_integer(generate_answer(model, tok, e["question"])), e["answer"])) for e in examples]


def texts(model, tok, examples):
    return [generate_answer(model, tok, e["question"]) for e in examples]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", type=float, required=True)
    ap.add_argument("--generations", type=int, default=10)
    ap.add_argument("--population", type=int, default=8)
    ap.add_argument("--sigma", type=float, default=1e-3)
    ap.add_argument("--experiment-id", default="learn")
    ap.add_argument("--output", required=True)
    ap.add_argument("--save-outputs", default=None, help="JSON file for the held-out output texts at the start and at the end")
    a = ap.parse_args()
    assert not os.path.exists(a.output), "refusing to overwrite"
    train, held = dataset.train_heldout()
    model = AutoModelForCausalLM.from_pretrained(SNAP, dtype=torch.float16).to("cuda"); tok = AutoTokenizer.from_pretrained(SNAP)
    schema = build_parameter_schema(model)
    parent = take_snapshot(model, schema)
    mean = lambda v: sum(v) / len(v)
    t0 = time.perf_counter()
    cur_train, cur_held = evaluate(model, tok, train), evaluate(model, tok, held)
    start_texts = texts(model, tok, held) if a.save_outputs else None
    log = {"config": vars(a), "schema_hash": schema.hash, "train_size": len(train), "held_size": len(held),
           "start": {"train": cur_train, "held": cur_held}, "generations": []}
    print(f"start: train {mean(cur_train):.4f}  held-out {mean(cur_held):.4f}", flush=True)
    for g in range(a.generations):
        tg = time.perf_counter()
        seeds = [derive_seed(a.experiment_id, g, i) for i in range(a.population)]
        rewards = []
        for s in seeds:
            perturb_model_(model, schema, s, a.sigma)
            rewards.append(mean(evaluate(model, tok, train)))
            restore_from_snapshot_(model, schema, parent)
        rep = apply_es_update_(model, schema, seeds, rewards, a.alpha)
        plus_train, plus_held = evaluate(model, tok, train), evaluate(model, tok, held)
        plus_snapshot = take_snapshot(model, schema)
        restore_from_snapshot_(model, schema, parent)
        rep_minus = apply_es_update_(model, schema, seeds, rewards, -a.alpha)
        minus_train, minus_held = evaluate(model, tok, train), evaluate(model, tok, held)
        restore_from_snapshot_(model, schema, plus_snapshot)
        record = {"generation": g, "seeds": seeds, "candidate_rewards": rewards, "noop": rep.noop,
                  "coefficients": list(rep.coefficients), "requested_l2": rep.requested_l2, "applied_l2": rep.applied_l2,
                  "changed": rep.changed, "numel": rep.numel,
                  "parent": {"train": cur_train, "held": cur_held},
                  "plus": {"train": plus_train, "held": plus_held}, "minus": {"train": minus_train, "held": minus_held},
                  "seconds": time.perf_counter() - tg}
        log["generations"].append(record)
        parent, cur_train, cur_held = plus_snapshot, plus_train, plus_held
        print(f"gen {g}: cand rewards mean {np.mean(rewards):.3f} std {np.std(rewards):.3f} "
              f"[{min(rewards):.3f}..{max(rewards):.3f}] | train parent {mean(record['parent']['train']):.3f} -> +{mean(plus_train):.3f} / -{mean(minus_train):.3f}"
              f" | held parent {mean(record['parent']['held']):.3f} -> +{mean(plus_held):.3f} / -{mean(minus_held):.3f}"
              f" | applied/requested L2 {rep.applied_l2/max(rep.requested_l2,1e-30):.2f} changed {rep.changed/rep.numel:.3f} | {record['seconds']:.0f}s", flush=True)
        json.dump(log, open(a.output, "w"))
    if a.save_outputs:   # the model is on the real trajectory again (plus_snapshot restored)
        end_texts = texts(model, tok, held)
        json.dump({"held": held, "start": start_texts, "end": end_texts}, open(a.save_outputs, "w"))
    log["total_seconds"] = time.perf_counter() - t0
    json.dump(log, open(a.output, "w"))
    print(f"done in {log['total_seconds']:.0f}s -> {a.output}", flush=True)


if __name__ == "__main__":
    main()
