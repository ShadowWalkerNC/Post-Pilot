"""
integrations/base.py — Abstract Base Client for Social & Platform Integrations.

Defines the contract for platform providers (Meta, Google, TikTok, Twitter, Website).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime


class ProviderClient(ABC):
    """
    Abstract contract that all third-party provider clients conform to.
    """

    @abstractmethod
    def publish(
        self,
        text: str,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        link_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Immediately publish a post to the platform.
        Returns dict with at least {'success': bool, 'post_id': Optional[str], 'error': Optional[str]}.
        """
        pass

    @abstractmethod
    def schedule(
        self,
        text: str,
        publish_time: datetime,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Schedule a post for future delivery on the platform.
        Returns dict with at least {'success': bool, 'post_id': Optional[str], 'error': Optional[str]}.
        """
        pass

    @abstractmethod
    def get_insights(self, days: int = 30) -> Dict[str, Any]:
        """
        Fetch engagement and reach metrics for the account.
        """
        pass
