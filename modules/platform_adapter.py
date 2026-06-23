"""
modules/platform_adapter.py

Auto-adapts a master caption for every enabled social platform.

Design:
  - One OpenAI call per platform, run in parallel via ThreadPoolExecutor.
  - Each platform has a PLATFORM_RULES entry defining tone, length,
    hashtag count, and any hard constraints (e.g. Twitter 280-char limit).
  - adapt_all() returns a dict {platform_key: adapted_text}.
  - Falls back to the master caption if OpenAI is unavailable or a
    single platform call fails -- publishing always continues.

Usage:
    from modules.platform_adapter import PlatformAdapter

    adapter  = PlatformAdapter()
    adapted  = adapter.adapt_all(
        master    = "Come try our new tacos! Fresh ingredients, open till 9.",
        platforms = ['fb', 'ig', 'tt', 'li'],
        tone      = 'friendly',
        business  = {'name': 'Taco Truck', 'type': 'food_truck', 'location': 'Main St'},
    )
    # adapted == {'fb': '...', 'ig': '...', 'tt': '...', 'li': '...'}
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-platform prompt rules
# ---------------------------------------------------------------------------
PLATFORM_RULES: Dict[str, Dict] = {
    'fb': {
        'name':      'Facebook',
        'max_chars': 500,
        'rules': (
            'Write in a warm, conversational tone. '
            '1-3 short paragraphs. Emojis welcome but not excessive (3-6 max). '
            'End with a soft call-to-action (visit us, tag a friend, comment below). '
            'Do NOT add more than 5 hashtags -- Facebook deprioritises hashtag-heavy posts.'
        ),
    },
    'ig': {
        'name':      'Instagram',
        'max_chars': 2200,
        'rules': (
            'Start with a strong one-line hook (the first line is shown before "more"). '
            'Use line breaks for readability. Emojis encouraged. '
            'Add 15-25 relevant hashtags at the end, separated from the body by a blank line. '
            'End the body (before hashtags) with a clear CTA like "Save this post" or "Tag someone".'
        ),
    },
    'tt': {
        'name':      'TikTok',
        'max_chars': 2200,
        'rules': (
            'First 3 words must be a scroll-stopping hook -- make it urgent or curious. '
            'Keep the caption SHORT (under 150 chars is ideal for in-video overlay). '
            'End with a direct CTA: "Follow for more", "Comment your answer", etc. '
            'Add 3-5 trending hashtags only -- do NOT use generic hashtags like #fyp alone. '
            'Tone: energetic, casual, Gen-Z friendly.'
        ),
    },
    'yt': {
        'name':      'YouTube',
        'max_chars': 5000,
        'rules': (
            'Write a full YouTube video description. '
            'First 2 sentences are the most important -- they show before "Show more". '
            'Front-load keywords naturally. '
            'Include a short section with timestamps if relevant (e.g. 0:00 Intro). '
            'Add a "Links & Resources" section placeholder. '
            'End with 5-10 relevant hashtags. '
            'Tone: informative, friendly, slightly more formal than TikTok.'
        ),
    },
    'yts': {
        'name':      'YouTube Shorts',
        'max_chars': 500,
        'rules': (
            'Write a YouTube Shorts description. '
            'Very short -- 1-2 punchy sentences max. '
            'Must include #Shorts as the first hashtag. '
            'Add 3-4 more relevant hashtags. '
            'Tone: energetic, matches TikTok energy.'
        ),
    },
    'li': {
        'name':      'LinkedIn',
        'max_chars': 3000,
        'rules': (
            'Professional tone -- no slang, no excessive emojis (max 2-3). '
            'Start with an insight, question, or bold statement to hook professionals. '
            'Write 3-5 short paragraphs. Use line breaks generously. '
            'Add a business or industry takeaway. '
            'End with a thoughtful question to drive comments. '
            'Max 5 hashtags, all professional/industry relevant (e.g. #SmallBusiness #FoodIndustry). '
            'Do NOT use casual CTAs like "tag a friend" -- use "Share your thoughts" or "I\'d love to hear from you".'
        ),
    },
    'tw': {
        'name':      'Twitter / X',
        'max_chars': 280,
        'rules': (
            'STRICT 280 character limit -- count carefully. '
            'One punchy sentence or two very short ones. '
            'No filler words. Every word must earn its place. '
            'Max 2 hashtags -- Twitter algorithm penalises hashtag spam. '
            'Optional: end with a question to drive replies. '
            'Tone: bold, direct, slightly witty if appropriate.'
        ),
    },
    'pi': {
        'name':      'Pinterest',
        'max_chars': 500,
        'rules': (
            'Keyword-rich description -- Pinterest is a search engine, not just social. '
            'Lead with the benefit or outcome (e.g. "Perfect for summer entertaining..."). '
            '100-500 characters. No hashtags -- Pinterest deprecated them. '
            'Tone: aspirational, descriptive, positive. '
            'Include relevant keywords naturally (ingredient names, occasion, style).'
        ),
    },
    'gb': {
        'name':      'Google Business',
        'max_chars': 1500,
        'rules': (
            'Local SEO optimised -- naturally include city/neighbourhood name if known. '
            'Mention business hours, address, or "visit us" where appropriate. '
            'Clear call-to-action: "Order now", "Visit us today", "Call to reserve". '
            'Tone: friendly but professional. '
            '1-2 short paragraphs. No hashtags. '
            'Focus on what makes this post useful for someone searching locally.'
        ),
    },
    'web': {
        'name':      'Website Banner',
        'max_chars': 300,
        'rules': (
            'Write TWO parts separated by a blank line:\n'
            '1. HEADLINE: One punchy sentence, max 80 characters, no emojis.\n'
            '2. BODY: 1-2 sentences expanding on the headline, friendly tone. '
            'This will appear as a website announcement banner. '
            'No hashtags. Clear and welcoming.'
        ),
    },
}

# All known platform keys in display order
ALL_PLATFORMS: List[str] = ['fb', 'ig', 'tt', 'yt', 'yts', 'li', 'tw', 'pi', 'gb', 'web']


# ---------------------------------------------------------------------------
# PlatformAdapter
# ---------------------------------------------------------------------------

class PlatformAdapter:
    """
    Adapts a single master caption into platform-specific versions.

    Each platform gets its own OpenAI call with tailored rules.
    All calls run in parallel via ThreadPoolExecutor.
    Falls back to master caption if OpenAI is unavailable.
    """

    def __init__(self, model: str = 'gpt-4o-mini', max_workers: int = 8):
        self.model       = model
        self.max_workers = max_workers
        self._client     = None

    def _get_client(self):
        """Lazy-load OpenAI client (avoids import error if key not set)."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
            except ImportError:
                logger.error('platform_adapter: openai package not installed')
                return None
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def adapt_all(
        self,
        master:    str,
        platforms: List[str],
        tone:      str = 'friendly',
        business:  Optional[Dict] = None,
    ) -> Dict[str, str]:
        """
        Adapt master caption for all requested platforms in parallel.

        Args:
            master:    The base caption to adapt.
            platforms: List of platform keys to adapt for (e.g. ['fb', 'ig', 'tt']).
            tone:      Overall tone hint passed to each prompt.
            business:  Optional dict with keys: name, type, location, city.
                       Used to personalise prompts where relevant.

        Returns:
            Dict mapping platform key -> adapted caption string.
            Falls back to master caption for any platform that fails.
        """
        client = self._get_client()
        if client is None:
            logger.warning('platform_adapter: OpenAI unavailable -- returning master caption for all platforms')
            return {p: master for p in platforms}

        results: Dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_platform = {
                executor.submit(self._adapt_one, client, master, p, tone, business): p
                for p in platforms
                if p in PLATFORM_RULES
            }
            # Platforms not in PLATFORM_RULES (unknown keys) fall back immediately
            for p in platforms:
                if p not in PLATFORM_RULES:
                    logger.warning('platform_adapter: unknown platform key %r -- using master', p)
                    results[p] = master

            for future in as_completed(future_to_platform):
                platform = future_to_platform[future]
                try:
                    results[platform] = future.result()
                except Exception as e:
                    logger.error('platform_adapter: adapt failed for %s: %s', platform, e)
                    results[platform] = master  # safe fallback

        return results

    def adapt_one(
        self,
        master:   str,
        platform: str,
        tone:     str = 'friendly',
        business: Optional[Dict] = None,
    ) -> str:
        """
        Adapt master caption for a single platform.
        Useful for re-adapting after a user edits the master.
        """
        client = self._get_client()
        if client is None or platform not in PLATFORM_RULES:
            return master
        try:
            return self._adapt_one(client, master, platform, tone, business)
        except Exception as e:
            logger.error('platform_adapter: adapt_one failed for %s: %s', platform, e)
            return master

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _adapt_one(
        self,
        client,
        master:   str,
        platform: str,
        tone:     str,
        business: Optional[Dict],
    ) -> str:
        rules     = PLATFORM_RULES[platform]
        biz_ctx   = self._business_context(business)
        max_chars = rules['max_chars']

        system_prompt = (
            f'You are a social media copywriter specialising in {rules["name"]} content. '
            f'You adapt provided captions to suit the platform perfectly. '
            f'Always return ONLY the adapted caption text -- no explanations, '
            f'no labels, no quotes around the output.'
        )

        user_prompt = (
            f'Adapt the following caption for {rules["name"]}. '
            f'Tone: {tone}. '
            f'Max characters: {max_chars}.\n'
            f'{biz_ctx}'
            f'\nPlatform rules:\n{rules["rules"]}\n'
            f'\nMaster caption to adapt:\n{master}\n'
            f'\nReturn ONLY the adapted {rules["name"]} caption:'
        )

        response = client.chat.completions.create(
            model       = self.model,
            messages    = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user',   'content': user_prompt},
            ],
            max_tokens  = max(256, max_chars // 2),
            temperature = 0.7,
        )
        adapted = response.choices[0].message.content.strip()

        # Hard-enforce character limit for platforms where it matters (tw)
        if platform == 'tw' and len(adapted) > 280:
            adapted = adapted[:277] + '...'

        return adapted

    @staticmethod
    def _business_context(business: Optional[Dict]) -> str:
        """Build a short business context string for the prompt."""
        if not business:
            return ''
        parts = []
        if business.get('name'):
            parts.append(f'Business name: {business["name"]}')
        if business.get('type'):
            parts.append(f'Business type: {business["type"].replace("_", " ").title()}')
        if business.get('location') or business.get('city'):
            loc = business.get('location') or business.get('city', '')
            parts.append(f'Location: {loc}')
        return ('Business context: ' + ', '.join(parts) + '.\n') if parts else ''
