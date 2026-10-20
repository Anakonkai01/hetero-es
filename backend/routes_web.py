from .config import load_config
import json
import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def install_routes(app, web_directory, downloads_directory):
    if web_directory is not None:
        web = Path(web_directory).resolve(strict=True)
        if not (web / "index.html").is_file():
            raise ValueError("Built web application is missing")
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="web-assets")
        if downloads_directory is not None:

            @app.get("/downloads/manifest.json", include_in_schema=False)
            def installer_manifest():
                manifest = json.loads((Path(downloads_directory) / "manifest.json").read_text())
                private_root = os.environ.get("HETEROES_PRIVATE_CONFIG")
                if private_root:
                    config = load_config(private_root)
                    # publicDownloads: the operator serves installers on the public origin too.
                    if config.get("publicWebUrl") and not config.get("publicDownloads"):
                        bulk = config.get("bulkApiUrl", config.get("apiUrl"))
                        manifest["privateTransferRequired"] = True
                        for group in ("installers", "serverInstallers"):
                            for item in manifest.get(group, []):
                                item["url"] = bulk + "/downloads/" + Path(item["name"]).name
                        for item in manifest.get("linuxWorker", {}).values():
                            item["url"] = bulk + "/downloads/" + Path(item["name"]).name
                return manifest

            # The publisher links installers from another disk; Starlette refuses such symlinks by default.
            # Path traversal is still rejected: the check then compares the link's own location.
            app.mount(
                "/downloads", StaticFiles(directory=downloads_directory, follow_symlink=True), name="worker-downloads"
            )
        else:

            @app.get("/downloads/manifest.json", include_in_schema=False)
            def no_installers():
                return {"version": "0.1.0", "privateTrial": True, "installers": []}

        @app.get("/{route:path}", include_in_schema=False)
        def web_page(route: str):
            if route == "api" or route.startswith(("api/", "assets/", "downloads/")):
                raise HTTPException(404, "Unknown endpoint")
            candidate = web / route
            if candidate.is_file() and candidate.resolve().is_relative_to(web):
                return FileResponse(candidate)
            return FileResponse(web / "index.html", headers={"Cache-Control": "no-cache"})
