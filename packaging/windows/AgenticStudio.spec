# Windows x64, one-folder application. Only allowlisted application resources
# and installed runtime packages enter the bundle; never copy the repository.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata


sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))
recipe = Path(SPECPATH)
root = recipe.parents[1]
staging = Path(os.environ["AGENTIC_RELEASE_STAGING"])

datas = [
    (str(root / "src/agentic_web_demo/dashboard/static"), "agentic_web_demo/dashboard/static"),
    (str(root / "src/agentic_web_demo/portal/templates"), "agentic_web_demo/portal/templates"),
    (str(root / "src/agentic_web_demo/portal/static"), "agentic_web_demo/portal/static"),
    (str(root / "config/rules.yaml"), "config"),
    (str(staging / "app.ico"), "."),
]
binaries = []
hiddenimports = [
    "agentic_web_demo.dashboard.app",
    "keyring.backends.Windows",
    "win32timezone",
    "tiktoken_ext.openai_public",
]


def runtime_module(name):
    return not any(part in {"tests", "test", "__pycache__"} for part in name.split("."))


# These packages load code/data dynamically. Keep both supported frameworks;
# collect-all is deliberately limited to these runtime packages, not the venv.
# Playwright's installed .local-browsers is inside its package for this build.
for package in ("playwright", "crewai", "litellm"):
    package_data, package_binaries, package_imports = collect_all(
        package,
        filter_submodules=runtime_module,
        exclude_datas=["**/tests/**", "**/__pycache__/**"],
    )
    datas.extend(package_data)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_imports)

for package in ("agentic_web_demo", "uvicorn", "langgraph"):
    hiddenimports.extend(collect_submodules(package, filter=runtime_module))

# Version/dependency checks inside CrewAI and its providers use package metadata.
# Include metadata/licenses for the locked application dependency closure.
datas.extend(copy_metadata("agenticai-web-demo", recursive=True))

analysis = Analysis(
    [str(recipe / "entrypoint.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(recipe / "runtime_hook.py")],
    excludes=["pytest", "IPython", "notebook"],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AgenticStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(staging / "app.ico"),
    contents_directory="_internal",
)
application = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="AgenticStudio",
)
