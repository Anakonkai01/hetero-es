"""Desktop v3 admission must bind repeated texts, signs and exact restore to its reference."""

import copy

import pytest


def test_reference_verification_rejects_text_sign_and_restore_drift():
    from heteroes.product.qualification_v3 import verify

    positive = {
        "recipeHash": "recipe",
        "modelManifestHash": "model",
        "parentSha256": "parent",
        "restoredSha256": "parent",
        "perturbedSha256": "positive",
        "outputsHash": "texts+",
        "reward": 1.0,
    }
    negative = {**positive, "perturbedSha256": "negative", "outputsHash": "texts-"}
    reference = {"expected": positive, "negativeExpected": negative}
    observations = {1: [positive.copy(), positive.copy()], -1: [negative.copy(), negative.copy()]}
    assert verify(reference, observations)["repeatIdentical"]
    for sign in (1, -1):
        for key in positive:
            wrong = copy.deepcopy(observations)
            wrong[sign][0][key] = "drift"
            wrong[sign][1][key] = "drift"
            with pytest.raises(ValueError):
                verify(reference, wrong)
        wrong = copy.deepcopy(observations)
        wrong[sign].pop()
        with pytest.raises(ValueError):
            verify(reference, wrong)
    bad_ref = copy.deepcopy(reference)
    bad_ref["expected"]["restoredSha256"] = "other"
    bad_obs = copy.deepcopy(observations)
    for row in bad_obs[1]:
        row["restoredSha256"] = "other"
    with pytest.raises(ValueError, match="restore"):
        verify(bad_ref, bad_obs)


# The round trip below uses the offline tiny model: it proves the mechanism, never a device's compatibility.
REVISION = "0" * 40


@pytest.fixture(scope="module")
def reference_dir(tmp_path_factory):
    from heteroes.model.lora import create_initial_adapter
    from heteroes.product.qualification_v3 import ADAPTER_SPACE, build_reference, write_reference
    from heteroes.v3.model import file_manifest, load
    from tinylm import build_tiny_lm

    root = tmp_path_factory.mktemp("qualification")
    build_tiny_lm(root / "model")
    donor, _ = load(root / "model", file_manifest(root / "model"))
    create_initial_adapter(donor, ADAPTER_SPACE, 7, root / "adapter.bin")
    reference = build_reference(root / "model", "tiny/qwen2", REVISION, root / "adapter.bin", device="cpu")
    write_reference(reference, root / "adapter.bin", root / "published")
    return root


def load_reference(directory):
    import json

    return json.loads((directory / "published" / "reference-v3.json").read_text())


def test_a_device_matching_the_reference_qualifies_without_regenerating_the_adapter(reference_dir, monkeypatch):
    import heteroes.model.lora as lora
    from heteroes.canonical import canonical_json_hash
    from heteroes.product.qualification_v3 import qualify

    def refuse(*args, **kwargs):
        raise AssertionError("a worker never makes an adapter from a seed")

    monkeypatch.setattr(lora, "create_initial_adapter", refuse)
    reference = load_reference(reference_dir)
    for cell in reference["cells"].values():  # premise: both signs really perturb the weights
        assert cell["expected"]["perturbedSha256"] != cell["negativeExpected"]["perturbedSha256"]
    assert reference["cells"]["lora"]["recipe"]["weightSpace"]["initialAdapterSha256"] == reference["adapter"]["sha256"]
    result = qualify(reference_dir / "model", reference, reference_dir / "published", device="cpu")
    assert (result["passed"], result["recipeVersions"], result["runtimeProfile"]) == (True, [3], "desktop-v3")
    full, adapter = result["compatibility"]["recipeV3"], result["compatibility"]["recipeV3Lora"]
    for evidence, cell in ((full, "full"), (adapter, "lora")):
        assert evidence["recipeHash"] == canonical_json_hash(reference["cells"][cell]["recipe"])
    assert full["outputsHash"] == reference["cells"]["full"]["expected"]["outputsHash"]
    assert adapter["outputsHash"] == reference["cells"]["lora"]["expected"]["outputsHash"]
    assert full["parentSha256"] == full["restoredSha256"] and adapter["parentSha256"] == adapter["restoredSha256"]
    assert result["qualifiedModelHashes"] == [full["modelManifestHash"]] == [adapter["modelManifestHash"]]
    assert result["compatibility"]["initialAdapterSha256"] == reference["adapter"]["sha256"]


@pytest.mark.parametrize(
    "drift, message",
    [
        ("text", "differs from the qualified reference"),
        ("adapter", "adapter file differs"),
        ("plan", "recipe/plan"),
        ("profile", "desktop-v3 reference"),
    ],
)
def test_any_drift_from_the_reference_refuses_qualification(reference_dir, tmp_path, drift, message):
    import shutil

    from heteroes.model.lora import create_initial_adapter
    from heteroes.product.qualification_v3 import ADAPTER_SPACE, qualify
    from heteroes.v3.model import file_manifest, load

    reference = load_reference(reference_dir)
    published = tmp_path / "published"
    shutil.copytree(reference_dir / "published", published)
    if drift == "text":
        reference["cells"]["lora"]["negativeExpected"]["outputsHash"] = "f" * 64
    elif drift == "adapter":  # another adapter in place of the pinned file
        donor, _ = load(reference_dir / "model", file_manifest(reference_dir / "model"))
        (published / reference["adapter"]["file"]).unlink()
        create_initial_adapter(donor, ADAPTER_SPACE, 8, published / reference["adapter"]["file"])
    elif drift == "plan":
        reference["cells"]["full"]["plan"]["alpha"] = 0.5
    else:
        reference["profile"] = "desktop-v1"
    with pytest.raises(ValueError, match=message):
        qualify(reference_dir / "model", reference, published, device="cpu")


def builder():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts/build_v3_reference.py"
    spec = importlib.util.spec_from_file_location("build_v3_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_reference_builder_is_gated_and_makes_adapters_only_on_linux(reference_dir, tmp_path, monkeypatch):
    import json

    script = builder()
    common = ["--model-path", str(reference_dir / "model"), "--model-id", "tiny/qwen2", "--revision", REVISION]
    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    with pytest.raises(ValueError, match="HETEROES_GPU_ACCEPTANCE"):
        script.main([*common, "--adapter-seed", "7", "--out", str(tmp_path / "gpu"), "--gpu"])
    monkeypatch.setattr(script.sys, "platform", "win32")
    with pytest.raises(ValueError, match="Linux"):
        script.main([*common, "--adapter-seed", "7", "--out", str(tmp_path / "windows"), "--cpu-fixture"])
    monkeypatch.setattr(script.sys, "platform", "linux")
    assert script.main([*common, "--adapter-seed", "7", "--out", str(tmp_path / "cpu"), "--cpu-fixture"]) == 0
    made = json.loads((tmp_path / "cpu" / "reference-v3.json").read_text())
    shipped = json.loads((reference_dir / "published" / "reference-v3.json").read_text())
    assert made["cells"] == shipped["cells"] and made["adapter"] == shipped["adapter"]  # same seed, same machine
    assert made["environment"]["device"] == "cpu"
    assert not (tmp_path / "gpu").exists() and not (tmp_path / "windows").exists()


def test_the_gated_builder_observes_on_the_gpu(reference_dir, tmp_path, monkeypatch):
    import heteroes.product.qualification_v3 as qualification

    def observed_on(model_path, model_id, revision, adapter, device, emit):
        raise RuntimeError(device)

    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    monkeypatch.setattr(qualification, "build_reference", observed_on)
    adapter = reference_dir / "adapter.bin"
    common = ["--model-path", str(reference_dir / "model"), "--model-id", "tiny/qwen2", "--revision", REVISION]
    with pytest.raises(RuntimeError, match="^cuda$"):
        builder().main([*common, "--adapter", str(adapter), "--out", str(tmp_path / "gpu"), "--gpu"])


@pytest.mark.parametrize("version", [None, 3])
def test_the_desktop_entry_point_selects_v3_only_for_a_v3_reference(tmp_path, monkeypatch, capsys, version):
    import io
    import json

    import heteroes.product.qualification as legacy
    import heteroes.product.qualification_v3 as v3

    reference = {"formatVersion": 3, "profile": "desktop-v3"} if version == 3 else {"profile": "desktop-v1"}
    (tmp_path / "reference.json").write_text(json.dumps(reference))
    calls = []
    monkeypatch.setattr(legacy, "qualify", lambda *a, **k: calls.append(("v1", a)) or {"runtimeProfile": "desktop-v1"})
    monkeypatch.setattr(v3, "qualify", lambda *a, **k: calls.append(("v3", a)) or {"runtimeProfile": "desktop-v3"})
    request = {"modelPath": "/model", "referencePath": str(tmp_path / "reference.json")}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    assert legacy.main() == 0
    assert calls == ([("v3", ("/model", reference, tmp_path))] if version == 3 else [("v1", ("/model", reference))])
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["result"]["runtimeProfile"] == ("desktop-v3" if version == 3 else "desktop-v1")


def test_the_desktop_entry_point_reports_a_v3_failure_as_a_code(tmp_path, monkeypatch, capsys):
    import io
    import json

    import heteroes.product.qualification as legacy
    import heteroes.product.qualification_v3 as v3

    (tmp_path / "reference.json").write_text(json.dumps({"formatVersion": 3, "profile": "desktop-v3"}))

    called = []

    def unavailable(*args, **kwargs):
        called.append(args)
        raise RuntimeError("CUDA_UNAVAILABLE")

    monkeypatch.setattr(v3, "qualify", unavailable)
    request = {"modelPath": "/model", "referencePath": str(tmp_path / "reference.json")}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request)))
    assert legacy.main() == 1
    assert called and json.loads(capsys.readouterr().out.strip())["code"] == "CUDA_UNAVAILABLE"
