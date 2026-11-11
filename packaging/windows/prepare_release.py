"""Prepare allowlisted release resources and third-party notices; no app imports."""

import argparse
import importlib.metadata
import json
import re
import shutil
import struct
import zipfile
from pathlib import Path


EXTENSION_FILES = (
    "agent_observe.js", "capture_dom.js", "executor.js", "manifest.json", "native_input.js",
    "popup.css", "popup.html", "popup.js", "sidepanel.css", "sidepanel.html", "sidepanel.js",
    "worker.js",
)


def prepare(root, staging):
    staging.mkdir(parents=True, exist_ok=True)
    png = (root / "extensions/page-capture/icons/icon-128.png").read_bytes()
    width, height = struct.unpack(">II", png[16:24])
    if png[:8] != b"\x89PNG\r\n\x1a\n" or not 1 <= width <= 256 or not 1 <= height <= 256:
        raise ValueError("The shared application icon must be a PNG no larger than 256 pixels")
    (staging / "app.ico").write_bytes(
        struct.pack("<HHHBBBBHHII", 0, 1, 1, width % 256, height % 256, 0, 0,
                    1, 32, len(png), 22) + png
    )


def finish(root, application, version):
    # Copy named extension sources only. Never archive the repository, local
    # captures, credentials, backups, .env, venv or developer browser profiles.
    extension = application / "BrowserCompanion"
    extension.mkdir(parents=True, exist_ok=True)
    for name in EXTENSION_FILES:
        shutil.copyfile(root / "extensions/page-capture" / name, extension / name)
    icons = extension / "icons"
    icons.mkdir(exist_ok=True)
    for name in ("logo.svg", "icon-16.png", "icon-32.png", "icon-48.png", "icon-128.png"):
        shutil.copyfile(root / "extensions/page-capture/icons" / name, icons / name)
    with zipfile.ZipFile(application.parent / f"BrowserCompanion-{version}.zip", "w",
                         compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(extension.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(extension).as_posix())
    for source, target in (("GettingStarted.txt", "GettingStarted.txt"),
                           ("ReleaseReadiness.txt", "ReleaseReadiness.txt")):
        shutil.copyfile(root / "packaging/windows" / source, application / target)
    notices = application / "ThirdPartyNotices"
    notices.mkdir(exist_ok=True)
    dependencies = []
    for distribution in sorted(importlib.metadata.distributions(),
                               key=lambda item: item.metadata.get("Name", "").lower()):
        name = distribution.metadata.get("Name", "unknown")
        dependencies.append({
            "name": name,
            "version": distribution.version,
            "license": distribution.metadata.get("License-Expression")
                       or distribution.metadata.get("License") or "See package license files",
        })
        directory = notices / re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        for file in distribution.files or ():
            if not (
                re.match(r"^(?:licen[cs]e|copying|notice)(?:[._-]|$)", Path(file).name, re.I)
                or any(part.lower() == "licenses" for part in Path(file).parts)
            ):
                continue
            actual = distribution.locate_file(file)
            if actual.is_file():
                directory.mkdir(exist_ok=True)
                # Distribution files can contain the same basename in separate
                # directories; retain a deterministic suffix rather than replace.
                target = directory / Path(file).name
                index = 2
                while target.exists():
                    target = directory / f"{Path(file).stem}-{index}{Path(file).suffix}"
                    index += 1
                shutil.copyfile(actual, target)
    (notices / "packages.json").write_text(json.dumps(dependencies, indent=2), encoding="utf-8")
    manifest = json.loads((extension / "manifest.json").read_text(encoding="utf-8"))
    (application / "release.json").write_text(json.dumps({
        "product": "Agentic Studio", "version": version, "platform": "windows-x64",
        "companion_version": manifest["version"], "backend": "127.0.0.1:8120",
        "storage": "%LOCALAPPDATA%/AgenticStudio/data",
        "ai_connection": "User-configured provider connection; internet required",
        "browser": "Bundled Playwright Chromium; existing browser uses Browser Companion",
        "acceptance": "Manual release acceptance is required before distribution",
    }, indent=2), encoding="utf-8")
    # A pilot user can extract this folder and double-click the executable.
    # Keep the entire one-folder bundle together, including _internal.
    with zipfile.ZipFile(application.parent / f"AgenticStudio-{version}-win-x64.zip", "w",
                         compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(application.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(application.parent).as_posix())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "finish"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--application", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args()
    if args.phase == "prepare":
        if args.staging is None:
            parser.error("prepare requires --staging")
        prepare(args.root, args.staging)
    else:
        if args.application is None or not args.version:
            parser.error("finish requires --application and --version")
        finish(args.root, args.application, args.version)


if __name__ == "__main__":
    main()
