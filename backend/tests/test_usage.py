"""Usage survives the coordinator report and experiment reconciliation routes without numerical imports."""

from labkit import pair, enable, queued, boot


def test_reported_usage_reaches_the_experiment_without_cpu_runtime_imports(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    run_id = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    usage = {"generatedTokens": 37, "gpuSeconds": 2.5, "partial": False}
    snapshot = {
        "state": {"status": "RUNNING"},
        "generations": [],
        "candidates": [],
        "attempts": [],
        "events": [],
        "artifacts": [],
        "usageSummary": usage,
    }
    boot(
        client,
        auth,
        "boot-1",
        contribution=True,
        reports=[
            {
                "sequence": 1,
                "assignmentId": assignment["assignmentId"],
                "epoch": assignment["epoch"],
                "snapshot": snapshot,
            }
        ],
    )
    store.dispatch_once()
    response = client.get(f"/api/v1/experiments/{run_id}", headers=admin)
    assert response.status_code == 200 and response.json()["usageSummary"] == usage
