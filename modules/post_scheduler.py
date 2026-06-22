"""
modules/post_scheduler.py  [TOMBSTONE]

This file is a compatibility shim. All logic has been consolidated into
modules/scheduler_worker.py. Import from there directly.

Kept so that any code still importing from modules.post_scheduler doesn't break.
"""
# ruff: noqa: F401
from modules.scheduler_worker import (  # noqa: F401
    PostScheduler,
    OPTIMAL_TIMES,
    DAY_MAP,
    init_scheduler,
    shutdown_scheduler,
)
