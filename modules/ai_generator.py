"""
ai_generator.py — AI Caption Generation

Generates platform-optimized captions using:
  - OpenAI GPT-4o-mini (primary, $0.002/caption)
  - Template fallback (no API key required)

Flow (Option B — per-platform editable captions):
  1. generate_caption() produces a neutral master caption.
  2. PlatformAdapter.adapt_all() rewrites it for each enabled platform
     in parallel (ThreadPoolExecutor).
  3. Dashboard pre-fills one editable textarea per platform.
  4. User edits any/all, clicks Publish.
  5. UniversalPublisher receives a captions dict {platform: text}.

Backwards-compatible: generate_caption() and the single-platform path
are unchanged.
"""

import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tone system prompts
# ---------------------------------------------------------------------------
TONE_PROMPTS = {
    'hype':      'You write energetic, hype social media captions with lots of excitement and urgency. Use fire/rocket emojis sparingly.',
    'friendly':  'You write warm, conversational social media captions. Friendly and approachable, like a neighbor.',
    'urgent':    'You write urgent, time-sensitive social media captions. Create FOMO. Limited time. Act now.',
    'funny':     'You write witty, humorous social media captions. Light puns welcome. Keep it fun and shareable.',
    'community': 'You write community-focused social media captions. Emphasize connection, local love, and belonging.',
}

# Per-platform style instructions (used by single-platform generate_caption)
PLATFORM_STYLES = {
    'facebook': (
        'Facebook post: 1-3 sentences. Conversational tone. '
        'Can include a question to drive comments. 1-2 relevant hashtags max.'
    ),
    'instagram': (
        'Instagram caption: Hook in first line (cuts off at ~125 chars). '
        'Expand below the fold. End with 5-10 relevant hashtags on a new line. '
        'Emojis welcome throughout.'
    ),
    'tiktok': (
        'TikTok video title/description: Short punchy hook under 150 chars. '
        'Extremely casual, trending language. 3-5 hashtags including niche ones.'
    ),
    'youtube': (
        'YouTube video description: First 2-3 sentences are the hook (shown before More). '
        'Mention what viewers will see/get. Include location and business name naturally.'
    ),
    'google': (
        'Google Business post: Professional but warm. 1-2 sentences. '
        'No hashtags (Google ignores them). ASCII-safe characters only (no special emojis). '
        'Max 1500 characters. Include a clear call to action.'
    ),
    'website': (
        'Website banner message: Ultra-short. 1 punchy sentence or less. '
        'No hashtags. Just the key info + action. Max 120 characters.'
    ),
}


# ---------------------------------------------------------------------------
# Master caption prompt (platform-neutral)
# ---------------------------------------------------------------------------
MASTER_STYLE = (
    'Write a clear, engaging, platform-neutral social media caption. '
    'No hashtags. No platform-specific formatting. '
    'Focus on the core message and CTA only. '
    'This caption will be adapted for specific platforms separately.'
)


# ---------------------------------------------------------------------------
# Primary: OpenAI GPT-4o-mini
# ---------------------------------------------------------------------------
def _generate_openai(
    business_info: dict,
    content_type:  str,
    tone:          str,
    keywords:      list,
    platform:      str,
) -> Optional[str]:
    """Call OpenAI API to generate a caption. Returns None on failure."""
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        business_name = business_info.get('name', 'our business')
        business_type = business_info.get('type', 'food business')
        location      = business_info.get('location', '')
        special       = business_info.get('special', '')

        tone_instruction = TONE_PROMPTS.get(tone, TONE_PROMPTS['friendly'])

        # platform='master' uses neutral prompt; otherwise use per-platform style
        if platform == 'master':
            platform_style = MASTER_STYLE
        else:
            platform_style = PLATFORM_STYLES.get(platform, '')

        system_msg = (
            f'{tone_instruction}\n\n'
            f'You are writing for: {business_name}, a {business_type}.'
            + (f' Located at: {location}.' if location else '')
            + f'\n\nPlatform rules: {platform_style}'
        )

        user_msg = (
            f'Write a {content_type} post.'
            + (f" Today's special: {special}." if special else '')
            + (f" Keywords to include: {', '.join(keywords)}." if keywords else '')
            + ' Return only the caption text, nothing else.'
        )

        response = client.chat.completions.create(
            model       = 'gpt-4o-mini',
            messages    = [
                {'role': 'system', 'content': system_msg},
                {'role': 'user',   'content': user_msg},
            ],
            max_tokens  = 300,
            temperature = 0.8,
        )

        caption = response.choices[0].message.content.strip()
        logger.info('OpenAI caption generated for platform=%s tone=%s', platform, tone)
        return caption

    except Exception as e:
        logger.error('OpenAI generation failed: %s', e)
        return None


# ---------------------------------------------------------------------------
# Fallback: Template-based generation
# ---------------------------------------------------------------------------
TEMPLATES = {
    'daily_special': {
        'facebook':  "\ud83c\udf7d\ufe0f Today's special at {name}: {special}! Come in and try it \u2014 you won't be disappointed. {location_tag}",
        'instagram': "\u2728 TODAY'S SPECIAL \u2728\n\n{special} \u2014 made fresh and ready for you at {name}.\n\nCome find us {location_tag} and treat yourself! \ud83d\ude4c\n\n#{hashtag1} #{hashtag2} #foodie #localfood #dailyspecial",
        'tiktok':    "{special} just dropped at {name} \ud83d\udd25 Don't miss it #{hashtag1} #foodtruck #todaysspecial",
        'google':    "Today's special: {special}. Visit {name} at {location} to enjoy it today.",
        'website':   "Today's Special: {special} \u2014 available now!",
        'youtube':   "Today at {name} we're serving up {special}. Come find us at {location} \u2014 here's everything you need to know!",
    },
    'location': {
        'facebook':  "\ud83d\udccd We're set up at {location} today! Come find us \u2014 open until {hours}. {name} is ready for you!",
        'instagram': "\ud83d\udccd FIND US TODAY\n\nWe're at {location} and ready to serve!\nOpen until {hours}.\n\nTag a friend who needs to know \ud83d\udc47\n\n#{hashtag1} #foodtruck #localeats #{hashtag2}",
        'tiktok':    "We're at {location} right now \ud83d\udccd Open until {hours}! #{hashtag1} #foodtruck",
        'google':    "We are at {location} today, open until {hours}. Come visit {name}!",
        'website':   "\ud83d\udccd Today's Location: {location} | Open until {hours}",
        'youtube':   "We're parked at {location} today until {hours}! Here's how to find us at {name}.",
    },
    'general': {
        'facebook':  "Come visit {name}! We'd love to see you. {location_tag}",
        'instagram': "Fresh eats. Good vibes. {name} \ud83d\ude4c\n\n#{hashtag1} #{hashtag2} #localfood #supportlocal",
        'tiktok':    "{name} bringing the good stuff \ud83d\udd25 #{hashtag1} #foodie",
        'google':    "Visit {name} for great food and friendly service. We look forward to seeing you!",
        'website':   "Welcome to {name} \u2014 great food, great vibes.",
        'youtube':   "Welcome to {name}! Here's what we've been up to lately.",
    },
}


def _generate_template(business_info: dict, content_type: str, platform: str) -> str:
    """Generate caption from template. Always returns something."""
    name     = business_info.get('name', 'Our Business')
    location = business_info.get('location', 'our location')
    hours    = business_info.get('hours', 'closing time')
    special  = business_info.get('special', 'our daily special')
    biz_type = business_info.get('type', 'food').lower().replace(' ', '')

    hashtag1     = name.lower().replace(' ', '')
    hashtag2     = biz_type if biz_type else 'foodtruck'
    location_tag = f'at {location}' if location else ''

    template_group = TEMPLATES.get(content_type, TEMPLATES['general'])
    template       = template_group.get(platform, template_group.get('facebook', ''))

    return template.format(
        name=name,
        location=location,
        hours=hours,
        special=special,
        hashtag1=hashtag1,
        hashtag2=hashtag2,
        location_tag=location_tag,
    )


# ---------------------------------------------------------------------------
# Public API — single platform (backwards-compatible)
# ---------------------------------------------------------------------------
def generate_caption(
    business_info: dict,
    content_type:  str  = 'general',
    tone:          str  = 'friendly',
    keywords:      list = None,
    platform:      str  = 'facebook',
) -> str:
    """
    Generate a platform-optimized caption for a single platform.
    Unchanged from original -- fully backwards-compatible.

    Args:
        business_info: dict with keys: name, type, location, hours, special
        content_type:  'daily_special' | 'location' | 'general'
        tone:          'hype' | 'friendly' | 'urgent' | 'funny' | 'community'
        keywords:      extra words to weave into the caption
        platform:      'facebook' | 'instagram' | 'tiktok' | 'youtube' | 'google' | 'website'

    Returns:
        Caption string, always.
    """
    keywords = keywords or []
    caption  = _generate_openai(business_info, content_type, tone, keywords, platform)
    if not caption:
        logger.info('Using template fallback for platform=%s', platform)
        caption = _generate_template(business_info, content_type, platform)
    return caption


# ---------------------------------------------------------------------------
# Public API — Option B multi-platform with per-platform editable captions
# ---------------------------------------------------------------------------
def generate_with_adaptations(
    business_info: dict,
    content_type:  str       = 'general',
    tone:          str       = 'friendly',
    keywords:      list      = None,
    platforms:     List[str] = None,
) -> Dict:
    """
    Generate a master caption then adapt it for every requested platform
    in parallel.  Returns both master and adapted dict for Option B flow.

    Args:
        business_info: dict with keys: name, type, location, hours, special
        content_type:  'daily_special' | 'location' | 'general'
        tone:          'hype' | 'friendly' | 'urgent' | 'funny' | 'community'
        keywords:      extra words to weave into the caption
        platforms:     list of platform keys to adapt for.
                       Defaults to all 10 if not specified.

    Returns:
        {
            'master':  '<neutral master caption>',
            'adapted': {
                'fb':  '<Facebook version>',
                'ig':  '<Instagram version>',
                'tt':  '<TikTok version>',
                ...   (one key per requested platform)
            }
        }
    """
    from modules.platform_adapter import PlatformAdapter, ALL_PLATFORMS

    keywords  = keywords or []
    platforms = platforms or ALL_PLATFORMS

    # Step 1: generate platform-neutral master caption
    master = _generate_openai(business_info, content_type, tone, keywords, 'master')
    if not master:
        # Template fallback -- use facebook template as master base
        master = _generate_template(business_info, content_type, 'facebook')
        logger.info('generate_with_adaptations: using template master')

    # Step 2: adapt in parallel for all requested platforms
    adapter = PlatformAdapter()
    adapted = adapter.adapt_all(
        master   = master,
        platforms = platforms,
        tone      = tone,
        business  = business_info,
    )

    return {'master': master, 'adapted': adapted}


# ---------------------------------------------------------------------------
# Public API — all platforms (updated to use master + adapter)
# ---------------------------------------------------------------------------
def generate_all_platforms(
    business_info: dict,
    content_type:  str  = 'general',
    tone:          str  = 'friendly',
    keywords:      list = None,
) -> dict:
    """
    Generate captions for all platforms.
    Now uses master + PlatformAdapter for consistency and speed.

    Returns dict with 'master' key plus one key per platform:
        { 'master': '...', 'fb': '...', 'ig': '...', ... }

    Legacy keys (facebook, instagram, etc.) are aliased for
    backwards-compatibility with any existing callers.
    """
    result   = generate_with_adaptations(business_info, content_type, tone, keywords)
    master   = result['master']
    adapted  = result['adapted']

    # Legacy long-name aliases so old callers don't break
    key_aliases = {
        'fb':  'facebook',
        'ig':  'instagram',
        'tt':  'tiktok',
        'yt':  'youtube',
        'gb':  'google',
        'web': 'website',
    }
    out = {'master': master}
    for short, text in adapted.items():
        out[short] = text
        if short in key_aliases:
            out[key_aliases[short]] = text   # backwards-compat alias

    return out
