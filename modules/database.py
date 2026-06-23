# modules/database.py
# Thin proxy so modules (website_manager, api_manager, etc.) can call
# `from modules.database import get_db` without importing app.py directly.
# The real connection lives in Flask's `g` object, created per-request by app.py.

from flask import g
from modules.db import get_connection


def get_db():
    """
    Return the unified connection wrapper for the current request context.
    If called outside a request (e.g. CLI / init), opens a direct connection.
    """
    try:
        if 'db' not in g:
            g.db = get_connection()
            g.db.request_scoped = True
        return g.db

    except RuntimeError:
        # Outside request context (init_db, tests, CLI)
        return get_connection()

