"""Read-only corrections to experiment monitoring; canonical run evidence is never rewritten."""

import re
from heteroes.v3.options import audit_selected


def experiment_view(body, snapshot):
    shown = {**body}
    snapshot = snapshot or {}
    state = snapshot.get("state") or {}
    if state.get("status") == body.get("status") and "failureReason" in state:
        shown["failureReason"] = state["failureReason"]
    summary = body.get("auditSummary")
    if not summary or body.get("recipeVersion") != 3:
        return shown

    # Historical managed v3 runs without auditRate retain the 1/20 default. Audit
    # addresses are run/gN/cN, independent of seed namespace. Count committed
    # addresses instead of generation_done logs, which can be lost on recovery.
    generations = snapshot.get("generations") or []
    complete = bool(generations)
    indices = set()
    selected = 0
    for generation in generations:
        match = re.fullmatch(re.escape(body["experimentId"]) + r"\.g(\d+)", generation.get("generationId", ""))
        count = generation.get("candidateCount")
        committed = generation.get("committedCandidateCount")
        if not match or type(count) is not int or type(committed) is not int or not 0 <= committed <= count:
            complete = False
            break
        index = int(match[1])
        indices.add(index)
        if committed == count:
            candidates = range(count)
        else:
            candidates = {
                int(m[1])
                for candidate in snapshot.get("candidates", [])
                if candidate.get("generationId") == generation["generationId"]
                and candidate.get("status") == "COMMITTED"
                and (
                    m := re.fullmatch(
                        re.escape(generation["generationId"]) + r"\.c(\d+)", candidate.get("candidateId", "")
                    )
                )
            }
            if len(candidates) != committed:
                complete = False
                break
        selected += sum(
            audit_selected(f"{body['experimentId']}/g{index}/c{candidate}", body.get("auditRate", 0.05))
            for candidate in candidates
        )
    complete = complete and indices == set(range(max(indices, default=-1) + 1))
    complete = complete and sum(g.get("status") == "COMPLETED" for g in generations) == snapshot.get(
        "completedGenerationCount", sum(g.get("status") == "COMPLETED" for g in generations)
    )
    complete = complete and selected >= summary["completed"]
    shown["auditSummary"] = {
        **summary,
        "selected": selected if complete else None,
        "selectionComplete": complete,
        "incomplete": selected - summary["completed"] if complete else None,
    }
    return shown
