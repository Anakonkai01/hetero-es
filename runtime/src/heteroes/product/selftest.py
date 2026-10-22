"""Real device compatibility gate, run with process-local GPU libraries."""

import json
import sys
from .remote import handle


def main():
    from heteroes.model.loading import load_pinned_model, build_recipe, check_noise_selftest, check_recipe_selftest
    from heteroes.runtime_info import environment_info

    check_noise_selftest()
    loaded = load_pinned_model(sys.argv[1], "cuda")
    recipe = build_recipe(
        loaded, sigma=0.001, eval_dtype="float32", noise_engine="cpu", workload="arith16", decode_engine="hf_generate"
    )
    check_recipe_selftest(recipe, "cuda")
    gpu = handle({"action": "probe"})
    from heteroes.model.loading import checked_cpu_noise_engines

    print(
        json.dumps(
            {
                "passed": True,
                "coordinator": gpu["vramTotalMb"] >= 11000,
                "gpuName": gpu["gpuName"],
                "vramTotalMb": gpu["vramTotalMb"],
                "gpuUUID": gpu["gpuUUID"],
                "gpuIndex": gpu["gpuIndex"],
                "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
                "supportedNoiseEngines": checked_cpu_noise_engines(),
                "environment": environment_info("cuda"),
            }
        )
    )


if __name__ == "__main__":
    main()
