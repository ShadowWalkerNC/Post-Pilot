"""
Meta API Module
Handles all Facebook and Instagram Graph API interactions.
Now shims to canonical integrations.meta.MetaAPI.
"""

from integrations.meta import MetaAPI

__all__ = ['MetaAPI']
