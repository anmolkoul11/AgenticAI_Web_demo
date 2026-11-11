"""Use the browser bundled by the release build, not a developer's browser cache."""

import os


os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
