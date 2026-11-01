"""Shared CLI for isolated API, devices, storage, scheduler and combined service processes."""

import argparse
import os


def main(service):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("HETEROES_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HETEROES_PORT", "18052")))
    arguments = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    from .factory import app_from_environment
    import uvicorn

    uvicorn.run(
        lambda: app_from_environment(service=service),
        factory=True,
        host=arguments.host,
        port=arguments.port,
        access_log=False,
    )
