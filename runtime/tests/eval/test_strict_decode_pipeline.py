"""Queuing the next captured step before reading the current one must not change tokens, EOS or failures."""

import os

import pytest
import torch

from test_strict_decoder import model_for

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)

IDS = [[0, 0, 3, 5], [7, 11, 13, 17], [0, 19, 23, 29], [0, 0, 0, 31], [37, 41, 2, 4], [0, 6, 8, 10]]


def engines(family):
    from heteroes.strict.strict_decoder_graph import StrictDecoderGraph
    from heteroes.strict.strict_decoder_packed import StrictDecoderPacked

    model = model_for(family).cuda()
    return StrictDecoderGraph(model, max_context=40, allow_fixture=True), StrictDecoderPacked(
        model, max_context=40, allow_fixture=True
    )


def eos_patterns(free):
    """EOS sets that end rows at the first step, the last step, staggered steps, all at once and never."""
    tokens = free.tolist()
    steps = len(tokens[0])
    patterns = [[], [tokens[0][0]], [row[-1] for row in tokens], [row[0] for row in tokens]]
    patterns.append(sorted({tokens[i % len(tokens)][(3 * i + 1) % steps] for i in range(4)}))
    patterns.append([tokens[1][steps // 2], tokens[4][1]])
    return patterns


@gpu
@pytest.mark.parametrize("family", ["qwen2", "llama-wide"])
@pytest.mark.parametrize("penalty", [1.0, 1.3])
def test_pipelined_steps_match_the_eager_loop_for_every_eos_pattern(family, penalty):
    backend, eager = engines(family)
    ids = torch.tensor(IDS, device="cuda")
    mask = ids != 0
    options = dict(attention_mask=mask, max_new_tokens=12, repetition_penalty=penalty)
    free = eager.generate(ids, eos_token_id=[], **options)[:, ids.shape[1] :]
    for eos in eos_patterns(free):
        expected = eager.generate(ids, eos_token_id=eos, **options)
        actual = backend.generate(ids, eos_token_id=eos, **options)
        assert torch.equal(actual, expected), eos
        state = backend._session
        assert not bool(state.seen.any()) and not bool(state.lengths.any())
    for tokens in (1, 2, 3):
        expected = eager.generate(ids, eos_token_id=[], **{**options, "max_new_tokens": tokens})
        assert torch.equal(backend.generate(ids, eos_token_id=[], **{**options, "max_new_tokens": tokens}), expected)


@gpu
@pytest.mark.parametrize("penalty", [1.0, 1.3])
def test_failure_reported_by_a_step_queued_before_eos_is_undone_and_recomputed(monkeypatch, penalty):
    """Only a speculative step can feed an already finished row; flag exactly those steps.

    The unpipelined loop never runs such a step, so it never fails. The pipelined loop must undo the
    speculative step (lengths, tokens, seen) and recompute it for the survivors with identical results.
    """
    from heteroes.strict import strict_decode_cuda, strict_decoder_graph

    backend, eager = engines("llama-wide")
    ids = torch.tensor(IDS, device="cuda")
    mask = ids != 0
    options = dict(attention_mask=mask, max_new_tokens=12, repetition_penalty=penalty)
    free = eager.generate(ids, eos_token_id=[], **options)[:, ids.shape[1] :]
    original_greedy = strict_decode_cuda.DecodeKernels.greedy
    original_undo = strict_decoder_graph._DecodeSession.undo
    ends = torch.empty(0, dtype=torch.long, device="cuda")
    undone = []

    def greedy(self, scores, seen, owners, tokens, result, flag, *args):
        if torch.cuda.is_current_stream_capturing():
            flag.add_(torch.isin(tokens[owners], ends).any().to(torch.int32))
        return original_greedy(self, scores, seen, owners, tokens, result, flag, *args)

    def undo(self, owners, *args):
        undone.append(list(owners))
        return original_undo(self, owners, *args)

    monkeypatch.setattr(strict_decode_cuda.DecodeKernels, "greedy", greedy)
    monkeypatch.setattr(strict_decoder_graph._DecodeSession, "undo", undo)
    for eos in eos_patterns(free)[1:]:
        ends = torch.tensor(eos, dtype=torch.long, device="cuda")
        backend.release_graph()  # recapture with the current EOS set inside the injected check
        expected = eager.generate(ids, eos_token_id=eos, **options)
        actual = backend.generate(ids, eos_token_id=eos, **options)
        assert torch.equal(actual, expected), eos
    assert undone


@gpu
def test_failure_in_an_unchanged_queued_step_still_raises_and_releases_the_capture(monkeypatch):
    from heteroes.strict import strict_decode_cuda
    from heteroes.strict.reference_ops import ReferenceArithmeticError

    backend, _ = engines("qwen2")
    ids = torch.tensor(IDS, device="cuda")
    backend.generate(ids, max_new_tokens=2, eos_token_id=[])
    state = backend._session
    state.drop_capture()
    original_greedy = strict_decode_cuda.DecodeKernels.greedy

    def greedy(self, scores, seen, owners, tokens, result, flag, *args):
        if torch.cuda.is_current_stream_capturing():  # fails from the fifth generated token on
            flag.add_((state.lengths[owners] > 7).any().to(torch.int32))
        return original_greedy(self, scores, seen, owners, tokens, result, flag, *args)

    monkeypatch.setattr(strict_decode_cuda.DecodeKernels, "greedy", greedy)
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        backend.generate(ids, max_new_tokens=12, eos_token_id=[])
    assert backend._session is None and state.closed
    assert all(not bool(t.any()) for t in state.caches)
    monkeypatch.undo()
    assert backend.generate(ids, max_new_tokens=3, eos_token_id=[]).shape == (len(IDS), 7)


@gpu
def test_queue_never_runs_a_step_past_the_token_limit(monkeypatch):
    from heteroes.strict import strict_decoder_graph

    backend, _ = engines("qwen2")
    ids = torch.tensor(IDS, device="cuda")
    replays = []
    original = strict_decoder_graph._DecodeSession.launch

    def launch(self):
        replays.append(True)
        return original(self)

    monkeypatch.setattr(strict_decoder_graph._DecodeSession, "launch", launch)
    for tokens in (1, 2, 3, 12):
        replays.clear()
        backend.generate(ids, max_new_tokens=tokens, eos_token_id=[])
        assert len(replays) == tokens - 1  # the first token comes from prefill
