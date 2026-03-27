"""Shared test configuration.

Stub out heavy third-party dependencies that are pulled in transitively by
app.scraper but are not needed for API-level tests.  Registering these in
sys.modules *before* any test module is collected prevents import errors.
"""

import sys
from unittest.mock import MagicMock

for _mod in (
    "curl_cffi",
    "curl_cffi.requests",
    "aiofiles",
    "aiofiles.os",
    "aiohttp",
):
    sys.modules.setdefault(_mod, MagicMock())
