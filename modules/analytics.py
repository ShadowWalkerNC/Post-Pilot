"""
modules/analytics.py  [TOMBSTONE]

This file is a compatibility shim. All logic has been consolidated into
modules/analytics_client.py. Import from there directly.

Kept so that any code still importing from modules.analytics doesn't break.
"""
# ruff: noqa: F401
from modules.analytics_client import Analytics  # noqa: F401
