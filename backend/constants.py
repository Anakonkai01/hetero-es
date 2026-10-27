"""CPU-safe product identities and lifecycle state sets."""

from heteroes.catalog import PINNED_MODEL_ID as MODEL, PINNED_REVISION as REVISION

ACTIVE = {"STARTING", "RUNNING", "CANCELLING", "RECOVERING", "DRAINING", "PAUSING"}
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}
QUIESCENT = TERMINAL | {"PAUSED"}
CORE_COMMAND_KINDS = frozenset({"SET_CONTRIBUTION", "COORDINATE", "START_WORKER", "STOP_WORKER", "CANCEL_ASSIGNMENT"})
COMMAND_KINDS = CORE_COMMAND_KINDS | {
    "RETRY_WORKER",
    "PAUSE_ASSIGNMENT",
    "UPDATE_BACKUP_POLICY",
    "UPDATE_MEMBERSHIP",
    "QUALIFY_MODEL",
    "CANCEL_MODEL_QUALIFICATION",
}
# Settings only Recipe v3 has; the update-formula ones came later, so a run saved before them may lack them
V3_KEYS = ("weightSpace", "antithetic", "scorer", "coefficientRule", "systemPrompt")
# researcher code frozen with a web-lab experiment (owner 2026-10-20): sent to the coordinator only, never to workers
V3_CODE_KEYS = ("pythonCode",)
V3_UPDATE_KEYS = (
    "noiseEngineVersion",
    "alphaSchedule",
    "alphaMinimum",
    "momentumBeta",
    "momentumWindow",
    "evalChunk",
    "evalChunks",
    "sampler",
    "candidateSeedNamespace",
    "promptFormat",
    "auditRate",  # operational coverage; optional in older product configurations, outside numerical recipes
    "hardCapSeconds",  # D11 watchdog settings: operational, outside numerical recipes
    "stallSeconds",
)

# The shipped desktop-v3 qualification reference (docs/evidence/2026-10-19-v3-qualification-reference): a native Windows
# worker is admitted to Recipe v3 only with evidence for exactly these cells, this adapter file and this model.
DESKTOP_V3_REFERENCE = {
    "recipeV3": {
        "recipeHash": "6f97bc8ac9c75a2892d0a06b2f030dce555f3d7fca8536238726bb3880559c80",
        "outputsHash": "e5b89e88ecc2cf7fd30bf01c6147a93753d1bf41f30bdcc39b7063cde4bf1bf7",
        "negativeProbeHash": "560b67b8a8beb220d0a678e6a1c595bec18e8a27492703f0b7bb2424c0b59e73",
    },
    "recipeV3Lora": {
        "recipeHash": "dad24b0cf76fbe35a0d76e01a42a0f5d092990354cbfe178c600d1d0e0a76cd8",
        "outputsHash": "b9b18064a137a7ac21fdfe9744ca90e470e223c86be3e0e02998f26f8c95db22",
        "negativeProbeHash": "ead8464219c0d811913dd130695594503d00be89dc3ab6eaee5a4653205c6f1d",
    },
    "initialAdapterSha256": "051b79e34551eddac13dc3029743c32418bb332b3947b5b6b1249c9145e86b1e",
    "peftVersion": "0.21.2",
    "modelManifestHash": "af52722f2880d488e45860b7b97460c6fe2744aae79f555dce44d47cd47c533c",
}

# Candidate14 integer CPU v2 reference: both signs repeated on the reference GPU.
DESKTOP_V3_REFERENCE_V2 = {
    "recipeV3": {
        "recipeHash": "794bd6614e6e0465fe73f590f0644e29d9aee1ba0bb9a1100e9a284716999b06",
        "outputsHash": "a819adf852d943749f73b4dd55771c1cc4dccc2c18b1fb7c35fd0c3cebcc1bb0",
        "negativeProbeHash": "f96c68ca0f20c73dc695767dfcc1b1c6b5aea997c7fd6e726c696089da44ff64",
    },
    "recipeV3Lora": {
        "recipeHash": "9008786686dd02ea81ed012413dca5581a0fd452e1fd88a8cdaeaeeb0c7b2f2d",
        "outputsHash": "7ac95670aefb5568325703d8be305bcb4395deab448feff4ffb3430ab1ac5bc4",
        "negativeProbeHash": "051bcedea232996b02268e8c45f215e9c0047f9ddc8869d2632d16a85e1b2109",
    },
    "initialAdapterSha256": "051b79e34551eddac13dc3029743c32418bb332b3947b5b6b1249c9145e86b1e",
    "peftVersion": "0.21.2",
    "modelManifestHash": "af52722f2880d488e45860b7b97460c6fe2744aae79f555dce44d47cd47c533c",
}
