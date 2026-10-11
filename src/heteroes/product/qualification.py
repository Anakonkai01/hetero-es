"""Numerical admission for the desktop profile; no new numerical implementation."""
import json
import sys
from pathlib import Path


def verify(reference, observations):
    if len(observations) != 2 or observations[0] != observations[1]:
        raise ValueError('Repeated candidate is not identical')
    observed = observations[0]
    for key in ('recipeHash', 'parentSha256', 'perturbedSha256', 'restoredSha256', 'reward'):
        if observed[key] != reference[key]:
            raise ValueError('Numerical compatibility mismatch: ' + key)
    if observed['restoredSha256'] != observed['parentSha256']:
        raise ValueError('Candidate restore mismatch')
    return {'passed': True, 'repeatIdentical': True, **observed}


def verify_prediction(reference, observation):
    import hashlib
    outputs = observation['outputs']
    if len(outputs) != 16 or outputs != reference['outputs'] or observation['reward'] != reference['reward'] or observation['restoredSha256'] != observation['parentSha256']:
        raise ValueError('Linux prediction probe mismatch')
    actual = hashlib.sha256(json.dumps(outputs, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if actual != reference['outputsSha256']:
        raise ValueError('Linux prediction reference checksum mismatch')
    return {'predictionProbePassed': True, 'probeOutputsSha256': actual}


def qualify(model_path, reference, device='cuda', emit=lambda value: None):
    import heteroes.executor as execution
    from heteroes.model.loading import load_pinned_model, build_recipe, check_noise_selftest
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.manifest import CandidateDescriptor
    from heteroes.runtime_info import environment_info
    from .recovery import source_identity
    from .remote import handle
    if device == 'cuda':
        import torch
        if not torch.cuda.is_available():raise RuntimeError('CUDA_UNAVAILABLE')
    check_noise_selftest()
    emit({'stage': 'model'})
    loaded = load_pinned_model(model_path, device)
    recipe = build_recipe(loaded, sigma=.001, eval_dtype='float32', noise_engine='cpu', workload='arith16', decode_engine='hf_generate')
    executor = execution.CandidateExecutor(loaded.model, loaded.tokenizer, loaded.schema, recipe, chunk=16)
    descriptor = CandidateDescriptor(recipe.hash, executor.parent_sha256, 'desktop-qualification', 0, 0, reference['seed'])
    observations = []
    prediction_probe = reference['predictionProbe']
    probe_observation = None
    evaluate = execution.evaluate_model
    try:
        for index in range(3):
            emit({'stage': 'candidate', 'iteration': index + 1, 'total': 3})
            captured = {}
            def checked_evaluate(*args, **kwargs):
                captured['perturbedSha256'] = model_weights_sha256(loaded.model, loaded.schema)
                outcome = evaluate(*args, **kwargs)
                captured['outputs'] = [record.output_text for record in outcome.records]
                return outcome
            execution.evaluate_model = checked_evaluate
            current = descriptor if index < 2 else CandidateDescriptor(recipe.hash, executor.parent_sha256, 'desktop-qualification', 0, 1, prediction_probe['seed'])
            reward = executor(current)
            observed = {'recipeHash': recipe.hash, 'parentSha256': executor.parent_sha256,
                'perturbedSha256': captured['perturbedSha256'],
                'restoredSha256': model_weights_sha256(loaded.model, loaded.schema), 'reward': reward, 'outputs': captured['outputs']}
            if index < 2: observations.append(observed)
            else: probe_observation = observed
    finally:
        execution.evaluate_model = evaluate
    compatibility = verify(reference, observations)
    compatibility.update(verify_prediction(prediction_probe, probe_observation))
    gpu = handle({'action': 'probe'}) if device == 'cuda' else {'gpuName': 'CPU reference', 'vramTotalMb': 1}
    return {'passed': True, 'coordinator': sys.platform != 'win32' and gpu['vramTotalMb'] >= 11000,
        'gpuName': gpu['gpuName'], 'vramTotalMb': gpu['vramTotalMb'],
        'noiseVersion': 'numpy_pcg64_normal_f32_to_f16_v1', 'platform': 'windows' if sys.platform == 'win32' else 'linux',
        'runtimeProfile': 'desktop-v1', 'compatibility': compatibility,
        'environment': {**environment_info(device), **source_identity(Path(__file__).resolve().parents[1])}}


def main():
    request = json.load(sys.stdin)
    reference = json.loads(Path(request['referencePath']).read_text())
    def emit(value): print(json.dumps({'progress': value}), flush=True)
    try:
        result = qualify(request['modelPath'], reference, emit=emit)
        print(json.dumps({'result': result}), flush=True)
    except Exception as error:
        print(json.dumps({'error': type(error).__name__, 'code': str(error) if str(error) in {'CUDA_UNAVAILABLE','GPU_MISSING'} else 'COMPATIBILITY_FAILED'}), flush=True)
        return 1
    return 0


if __name__ == '__main__': sys.exit(main())
