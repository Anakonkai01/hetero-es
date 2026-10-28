import cProfile, pstats, io, importlib.util, os, time, sys
from pathlib import Path
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load, file_manifest
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
bench = module('benchmark', 'runtime/scripts/benchmark_inference.py'); probe = module('probe', 'runtime/scripts/probe_strict_backend.py')
path = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
model, tok = load(path, file_manifest(path), 'cuda')
engine = IntegerDecoderGraph(model, magnitude_bits=22, max_context=512, max_graph_bytes=6 * 1024**3)
short = [tok(t)['input_ids'] for t in probe.PROMPTS]; rows = [short[i % 8] for i in range(32)]
T = int(sys.argv[1]) if len(sys.argv) > 1 else 1
run = bench.decoder_run(engine, pad=tok.pad_token_id or 0, tokens=T)
run(rows); run(rows)
pr = cProfile.Profile(); torch.cuda.synchronize(); pr.enable(); run(rows); torch.cuda.synchronize(); pr.disable()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats('tottime').print_stats(25); print(s.getvalue()[:5000])
