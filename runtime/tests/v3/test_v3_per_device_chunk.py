"""Per-device evaluation chunk (ADR-010): a recipe may allow several chunks, the chunk that produced a candidate's texts is
recorded with them, and an audit re-runs the candidate at that chunk on a worker that may use it."""

import copy

import pytest

from heteroes.ledger import Ledger
from heteroes.manifest import CandidateDescriptor
from heteroes.v3.audit import AuditAPI
from heteroes.v3.documents import from_v2, validate_recipe
from heteroes.worker import Worker, StepKind, local_transport
from heteroes.worker_api import WorkerAPI, completions_sha256
from test_v3_documents import v2_recipe


def fp32(doc, **evaluation):
    changed = copy.deepcopy(doc)
    changed["evaluation"].update(evalDtype="float32", **evaluation)
    return changed


def test_a_recipe_may_allow_several_exact_chunks_including_its_own():
    doc, _ = from_v2(v2_recipe().to_dict())
    assert validate_recipe(fp32(doc, chunk=32, chunks=[16, 32, 64]))
    for bad in (
        {"chunks": [16, 32]},  # no chunk of its own
        {"chunk": 32, "chunks": [16, 64]},  # its own chunk is not allowed
        {"chunk": 32, "chunks": [64, 32]},  # not ascending
        {"chunk": 32, "chunks": [32, 128]},  # 128 was never probed across GPUs
        {"chunk": 32, "chunks": [32, 32]},
        {"chunk": 32, "chunks": "32"},
    ):
        with pytest.raises(ValueError):
            validate_recipe(fp32(doc, **bad))


def submit(api, work, texts, worker, chunk=None):
    return api.handle(
        "submit_result",
        {
            **{k: work[k] for k in ("descriptor", "attempt_number", "token") if k in work},
            **({"audit_id": work["audit_id"]} if "audit_id" in work else {}),
            "completions": texts,
            "completions_sha256": completions_sha256(texts),
            **({"chunk": chunk} if chunk is not None else {}),
        },
        authenticated_worker_id=worker,
    )


@pytest.fixture
def lab(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    descriptors = [CandidateDescriptor("1" * 64, "2" * 64, "audit", 0, i, i) for i in range(2)]
    ledger.open_generation(descriptors)
    base = WorkerAPI(ledger, "audit", 0, 60, scorer=lambda descriptor, texts: 0.5, allowed_chunks=(16, 32, 64))
    yield ledger, base, descriptors
    ledger.close()


def test_the_chunk_of_a_result_is_recorded_and_must_be_allowed(lab):
    ledger, base, (first, second) = lab
    work = base.handle("lease", {"worker_id": "big", "generation": 0})["work"]
    assert submit(base, work, ["a"], "big", chunk=128)["error"]["message"].startswith("chunk 128 is not one")
    assert submit(base, work, ["a"], "big", chunk=64)["ok"]
    assert ledger.completion_chunk(CandidateDescriptor.from_dict(work["descriptor"]).candidate_id) == 64
    work = base.handle("lease", {"worker_id": "small", "generation": 0})["work"]
    assert submit(base, work, ["b"], "small")["ok"]  # no chunk: the recipe's own
    assert ledger.completion_chunk(CandidateDescriptor.from_dict(work["descriptor"]).candidate_id) is None


def test_an_audit_runs_at_the_original_chunk_on_a_worker_that_may_use_it(lab):
    ledger, base, (first, second) = lab
    work = base.handle("lease", {"worker_id": "big", "generation": 0})["work"]
    submit(base, work, ["a"], "big", chunk=64)
    work = base.handle("lease", {"worker_id": "big", "generation": 0})["work"]
    submit(base, work, ["b"], "big")
    audits = AuditAPI(base, ledger, "audit", 0, rate=1.0, workers=["big", "small", "other"])
    asked = []

    def evaluate(descriptor, chunk=None):
        index = (first.candidate_id, second.candidate_id).index(descriptor.candidate_id)
        asked.append((index, chunk))
        return ("a",) if index == 0 else ("b",)

    small = Worker("small", local_transport(audits), evaluate)
    small.client.max_chunk = 32
    assert small.step(0).kind is StepKind.AUDITED
    assert small.step(0).kind is StepKind.NO_WORK  # the chunk-64 result needs a worker that may use 64
    other = Worker("other", local_transport(audits), evaluate)
    other.client.max_chunk = 64
    assert other.step(0).kind is StepKind.AUDITED
    assert asked == [(1, None), (0, 64)]
    assert audits.audit_counts() == (2, 2)


def test_a_worker_whose_larger_chunk_does_not_fit_falls_back_to_the_recipes_own(monkeypatch):
    from types import SimpleNamespace

    from heteroes.executor import CandidateExecutor, ChunkTexts
    from heteroes.ledger import FailureKind
    from heteroes.worker import CandidateFailed

    executor = CandidateExecutor.__new__(CandidateExecutor)
    executor.recipe, executor.allowed_chunks, executor.chunk = SimpleNamespace(chunk=32), (16, 32, 64), 64
    tried = []

    def run(descriptor, chunk):
        tried.append(chunk)
        if chunk == 64:
            raise CandidateFailed(FailureKind.OUT_OF_MEMORY, "CUDA out of memory")
        return ChunkTexts(("a",), chunk)

    executor._run = run
    assert executor("d").chunk == 32 and executor.chunk == 32 and tried == [64, 32]
    with pytest.raises(CandidateFailed):
        executor("d", chunk=128)  # never a chunk the recipe does not allow
    tried.clear()
    executor.chunk = 64
    with pytest.raises(CandidateFailed):
        executor("d", chunk=64)  # an audit must use the original's chunk: no fallback
    assert tried == [64]


def test_the_agent_offers_a_chunk_from_the_devices_memory_or_the_owners_limit():
    from heteroes.product.agent import max_chunk

    assert max_chunk({"selfTest": {"vramTotalMb": 16303}}) == 64
    assert max_chunk({"selfTest": {"vramTotalMb": 12288}}) == 32
    assert max_chunk({"selfTest": {"vramTotalMb": 6144}}) == 16
    assert max_chunk({"selfTest": {"vramTotalMb": 16303}, "maxChunk": 32}) == 32
