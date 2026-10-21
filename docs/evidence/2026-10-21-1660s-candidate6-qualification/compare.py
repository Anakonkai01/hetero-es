"""Compare a nine-case guarded-decoder probe with the committed 5070 final receipts, field by field."""
import copy
import json
import sys

RESULT_FIELDS = ('descriptor', 'texts', 'sha256', 'restoredParentSha256')
CAPTURE_FIELDS = ('inputIds', 'attentionMask', 'newTokenIds', 'evaluationFp32Sha256', 'perturbedFp16Sha256')


def compare(reference, other):
    if len(reference['results']) != 9 or len(other['results']) != 9:
        return False, []
    rows = []
    for ref, got in zip(reference['results'], other['results']):
        checks = {f: ref[f] == got[f] for f in RESULT_FIELDS}
        checks.update({f: ref['capture'][f] == got['capture'][f] for f in CAPTURE_FIELDS})
        rows.append({'repeat': got['repeat'], 'allEqual': all(checks.values()), 'checks': checks})
    same_identity = all(reference[k] == other[k] for k in ('decoderSourceSha256', 'oldRecipeHash', 'recipe', 'plan'))
    return same_identity and all(r['allEqual'] for r in rows), rows


def negative_controls(reference, other):
    controls = []
    for field in RESULT_FIELDS + CAPTURE_FIELDS:
        altered = copy.deepcopy(other)
        target = altered['results'][4] if field in RESULT_FIELDS else altered['results'][4]['capture']
        value = target[field]
        if isinstance(value, str):
            target[field] = value[:-1] + ('0' if value[-1] != '0' else '1')
        elif isinstance(value, dict):
            target[field] = {**value, 'index': value['index'] + 1}
        elif field == 'texts':
            target[field] = [value[0] + ' '] + value[1:]
        else:
            row = value[0]
            target[field] = [row[:-1] + [row[-1] + 1]] + value[1:]
        controls.append({'alteredField': field, 'rejected': not compare(reference, altered)[0]})
    return controls


def main(reference_path, other_path, out_path):
    reference = json.load(open(reference_path))
    other = json.load(open(other_path))
    ok, rows = compare(reference, other)
    report = {
        'allEqual': ok,
        'evaluations': len(rows),
        'decoderSourceSha256': other['decoderSourceSha256'],
        'cpuThreads': other['cpuThreads'],
        'gpu': other['environment'].get('gpu_name'),
        'gpuCapability': other['environment'].get('gpu_capability'),
        'referenceCalls': [r['capture']['stats']['referenceCalls'] for r in other['results']],
        'availableCpuRamGiBAfterEachCandidate': [round(r['availableCpuRamBytesAfterRestore'] / 2**30, 3)
                                                 for r in other['results']],
        'peakGpuAllocatedGiB': max(r['peakGpuAllocatedBytes'] for r in other['results']) / 2**30,
        'comparisons': rows,
        'negativeControls': {'untouchedPairPasses': ok, 'inMemoryOnly': True,
                             'controls': negative_controls(reference, other)},
    }
    with open(out_path, 'x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(json.dumps({'allEqual': ok, 'controlsRejected': all(c['rejected'] for c in
                                                              report['negativeControls']['controls'])}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
