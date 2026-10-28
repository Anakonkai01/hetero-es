"""Fixture-only cross-device receipt. Run with --gpu and HETEROES_GPU_ACCEPTANCE=1; imports test factories.

This proves no real-model qualification. Every GPU result is checked against an independent CPU operator run.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu', action='store_true')
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    if a.out.exists() or not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1':
        p.error('Use a fresh output and explicit GPU acceptance')
    import torch
    import transformers
    from test_strict_decoder import model_for, classes
    ref_type, serial_type, batch_type = classes()
    from heteroes.eval.strict_decoder_graph import StrictDecoderGraph
    batch_type = StrictDecoderGraph
    def digest(t):
        return hashlib.sha256(t.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
    def weight_hash(model):
        h = hashlib.sha256()
        for tensor in model.parameters():
            h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
        return h.hexdigest()
    report = {'status': 'running', 'hardwareQualified': False, 'fixture': True,
              'limitations': 'Tiny random graph fixtures; four layouts, three families, two finite weight states. '
                             'No trained-model, learning, native Windows or universal GPU acceptance.',
              'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                              'torch': torch.__version__, 'transformers': transformers.__version__,
                              'gpu': torch.cuda.get_device_name(), 'cc': list(torch.cuda.get_device_capability())},
              'probeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'comparison': {}, 'builds': {}}
    try:
        for family in ('qwen2', 'llama', 'llama-wide', 'mistral'):
            cpu_model = model_for(family)
            model = copy.deepcopy(cpu_model).cuda()
            eager = ref_type(cpu_model, max_context=64, allow_fixture=True)
            serial = serial_type(model, max_context=64, allow_fixture=True)
            batch = batch_type(model, max_context=64, allow_fixture=True)
            ids = torch.tensor([[0, 0, 3, 5], [7, 11, 13, 17], [0, 19, 23, 29]], device='cuda')
            mask = ids != 0
            rows = [ids[0:1, 2:], ids[1:2], ids[2:3, 1:]]
            cases = []
            before = weight_hash(model)
            for state in ('parent', 'changed'):
                if state == 'changed':
                    with torch.no_grad():
                        model.model.layers[0].mlp.down_proj.weight.mul_(-1)
                        cpu_model.model.layers[0].mlp.down_proj.weight.mul_(-1)
                expected = torch.cat([eager.forward_tokens(row.cpu())[0] for row in rows])
                logits, caches = batch.forward_batch(rows)
                direct = torch.cat([serial.forward_tokens(row)[0] for row in rows])
                if digest(logits) != digest(expected) or digest(direct) != digest(expected):
                    raise ValueError(f'{family}/{state}: logits differ')
                options = dict(max_new_tokens=6, eos_token_id=[], repetition_penalty=1.2)
                tokens = batch.generate(ids, attention_mask=mask, **options)
                oracle = eager.generate(ids.cpu(), attention_mask=mask.cpu(), **options)
                if not torch.equal(tokens.cpu(), oracle):
                    raise ValueError(f'{family}/{state}: tokens differ')
                fed = [torch.cat((row, tokens[i:i+1, ids.shape[1]:-1]), dim=1) for i, row in enumerate(rows)]
                final_logits = torch.cat([eager.forward_tokens(row.cpu())[0] for row in fed])
                if digest(batch._session.last_logits) != digest(final_logits):
                    raise ValueError(f'{family}/{state}: captured logits differ')
                if any(bool(t.any()) for t in batch._session.caches) or bool(batch._session.seen.any()):
                    raise ValueError('Candidate cache was retained')
                cases.append({'graphLogitsSha256': digest(batch._session.last_logits), 'captures': batch._session.capture_count, 'state': state, 'weightsSha256': weight_hash(model), 'logitsSha256': digest(logits),
                              'tokenIds': tokens.tolist(),
                              'cacheHashes': [[(digest(k), digest(v)) for k, v in cache] for cache in caches]})
            with torch.no_grad():
                model.model.layers[0].mlp.down_proj.weight.mul_(-1)
            if weight_hash(model) != before:
                raise ValueError('Exact fixture restore failed')
            report['comparison'][family] = {'identity': batch.identity, 'cases': cases, 'restoreExact': True}
            report['builds'][family] = batch.kernel_identity()
            batch.release_graph()
            del model, cpu_model, serial, batch, eager, caches
        report['status'] = 'ok'
    except Exception as error:
        report.update(status='error', errorType=type(error).__name__, error=str(error))
    with a.out.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'out': str(a.out)}))
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
