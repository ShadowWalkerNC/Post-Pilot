"""
modules/reply_agent.py
AI Reply Agent & Sentiment Classifier for Social Media Comments.

Provides:
- 5-class sentiment analysis: positive, neutral, negative, question, spam
- Tone-matched AI draft generation: friendly, hype, urgent, funny, community
- LLM gateway drafting (task_type="content") with graceful deterministic fallback matrix
"""

import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Valid sentiments & tones
SENTIMENTS = ['positive', 'neutral', 'negative', 'question', 'spam']
TONES = ['friendly', 'hype', 'urgent', 'funny', 'community']

# Regex Patterns for Rule-Based Classification
SPAM_PATTERNS = [
    r'https?://\S+',
    r'www\.\S+',
    r'bit\.ly/\S+',
    r't\.me/\S+',
    r'wa\.me/\S+',
    r'\b(dm me|inbox me|send (a )?pic to|promote it on|check my bio|earn \$\d+|crypto|forex|invest|whatsapp me)\b',
    r'\b(follow (me|back)|gain followers|buy followers|free followers|sugar daddy|sugar mommy)\b',
]

QUESTION_PATTERNS = [
    r'\?',
    r'\b(when|where|what time|how much|is there|do you (have|do|serve)|are you (open|closed|located)|can we|could we)\b',
    r'\b(hours|address|location|parking|price|pricing|cost|menu|vegan|gluten[- ]?free|dairy[- ]?free|halal|kosher|delivery|takeout|reservation|reserve|table for)\b',
]

NEGATIVE_PATTERNS = [
    r'\b(terrible|horrible|awful|worst|disgusting|nasty|gross|stale|cold|soggy|burnt|raw|overcooked|undercooked)\b',
    r'\b(bad (service|food|experience|taste)|slow service|rude (staff|waiter|server)|overpriced|rip[- ]?off|waste of money)\b',
    r'\b(never (again|coming back)|disappointed|disappointing|got sick|food poisoning|waited forever|hair in|sucks?)\b',
    r'(\b1/10\b|\b0/10\b|\b0 stars\b|\b1 star\b)',
]

POSITIVE_PATTERNS = [
    r'\b(love|loved|amazing|delicious|yummy|fire|best|awesome|fantastic|incredible|favorite|favourite|great|perfection)\b',
    r'\b(10/10|so good|super good|super tasty|mouth[- ]?watering|top tier|the bomb|chef\'?s kiss|legendary|phenomenal)\b',
    r'[🔥❤️😍👏🙌🤤👌✨🎉🤩🥰]',
]


def classify_sentiment(comment_text: str) -> str:
    """
    Classify comment text into one of 5 classes:
    'spam', 'negative', 'question', 'positive', 'neutral'
    """
    text = (comment_text or '').strip()
    if not text:
        return 'neutral'

    # Check spam first
    for pat in SPAM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return 'spam'

    # Check negative second (prioritize customer service issues)
    for pat in NEGATIVE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return 'negative'

    # Check question third
    for pat in QUESTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return 'question'

    # Check positive fourth
    for pat in POSITIVE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return 'positive'

    return 'neutral'


def _get_fallback_reply(
    sentiment: str,
    tone: str = 'friendly',
    business_name: str = 'Our Business',
    business_type: str = 'restaurant',
    location: str = '',
    post_context: Optional[str] = None,
) -> str:
    """Generate deterministic draft reply from fallback template matrix."""
    tone = tone.lower() if tone in TONES else 'friendly'
    biz = business_name or 'Our Business'
    loc_str = f" in {location}" if location else ""

    if sentiment == 'spam':
        return ""

    if sentiment == 'positive':
        if tone == 'hype':
            return f"Thank you so much! 🔥 We love serving you the best! See you again soon! 🙌"
        elif tone == 'funny':
            return f"You just made our entire day! Our chef is literally dancing in the kitchen right now 🕺 See you soon at {biz}!"
        elif tone == 'community':
            return f"Our community means everything to us! Thank you for being part of the {biz} family! ❤️"
        elif tone == 'urgent':
            return f"Thanks for the love! Don't miss out on today's specials at {biz} while they last!"
        else: # friendly
            return f"Thank you for the wonderful feedback! We're so glad you enjoyed it and hope to see you again soon at {biz}! 😊"

    elif sentiment == 'question':
        if tone == 'hype':
            return f"Awesome question! Drop by {biz}{loc_str} or check the link in our bio for all the details and specials! 🔥"
        elif tone == 'funny':
            return f"Great question! If we gave away all our secrets here, we'd have to make you head chef 😉 Check our bio link or visit {biz} for all details!"
        elif tone == 'community':
            return f"Thanks for reaching out, neighbor! Feel free to DM us or stop by {biz}{loc_str} anytime — we're always here to help! ❤️"
        elif tone == 'urgent':
            return f"Thanks for asking! Our hours and specials are updated daily — check our bio link or stop by {biz} today!"
        else: # friendly
            return f"Great question! Please check out our website or visit us at {biz}{loc_str}, and our team will be happy to help! Let us know if you need anything else! 😊"

    elif sentiment == 'negative':
        if tone == 'urgent':
            return f"We take your feedback very seriously. Please DM us right away or contact our management team so we can resolve this immediately."
        elif tone == 'community':
            return f"We're so sorry to let you down. As a local business, your satisfaction is our top priority. Please send us a DM so we can make this right."
        else:
            return f"We are truly sorry to hear about your experience. We strive for excellence at {biz} and would love the chance to make things right. Please send us a direct message so we can connect."

    else: # neutral
        if tone == 'hype':
            return f"Thanks for stopping by! Big things cooking at {biz}! 🔥"
        elif tone == 'community':
            return f"Thanks for being here with us at {biz}! Have a wonderful day! ❤️"
        elif tone == 'funny':
            return f"Thanks for the comment! Good vibes and great food are always ready for you at {biz}! 😊"
        elif tone == 'urgent':
            return f"Thanks for stopping by! Check out what's new at {biz} today!"
        else: # friendly
            return f"Thanks for commenting and checking out {biz}! Hope to see you soon! 😊"


DRAFT_SCHEMA = {
    'type': 'object',
    'properties': {
        'sentiment': {'type': 'string'},
        'reply': {'type': 'string'},
    },
    'required': ['sentiment', 'reply'],
}


def _build_draft_messages(
    comment_text: str,
    tone: str,
    business_name: str,
    business_type: str,
    location: str,
    post_context: Optional[str] = None,
) -> tuple:
    """Build (system_prompt, user_content) for reply drafting.

    Byte-identical to the legacy per-provider prompt construction; the
    gateway forwards these verbatim to whichever provider serves the request.
    """
    system_prompt = (
        f"You are the social media community manager for {business_name}, a {business_type}"
        f"{f' in {location}' if location else ''}.\n"
        f"Tone style: {tone}.\n"
        f"Analyze the user comment, verify or refine its sentiment ('positive', 'neutral', 'negative', 'question', 'spam'), "
        f"and write a concise, authentic, on-brand social media response (1-2 sentences). If spam, reply should be empty string.\n"
        f"Output valid JSON strictly formatted as: {{\"sentiment\": \"...\", \"reply\": \"...\"}}"
    )
    user_content = f"Comment: \"{comment_text}\""
    if post_context:
        user_content = f"Original Post Context: \"{post_context}\"\n" + user_content
    return system_prompt, user_content


def _call_gateway_llm(
    comment_text: str,
    sentiment: str,
    tone: str,
    business_name: str,
    business_type: str,
    location: str,
    post_context: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Attempt LLM analysis & drafting via the gateway. Returns None on failure."""
    try:
        from ai.context import TaskRequirements
        from ai.gateway import build_gateway

        system_prompt, user_content = _build_draft_messages(
            comment_text, tone, business_name, business_type, location, post_context
        )
        data = build_gateway().structured_output(
            user_content,
            DRAFT_SCHEMA,
            system=system_prompt,
            requirements=TaskRequirements(task_type='content'),
            max_tokens=150,
            temperature=0.7,
        )
        if not isinstance(data, dict):
            return None
        refined = data.get('sentiment', sentiment)
        return {
            'sentiment': refined if refined in SENTIMENTS else sentiment,
            'reply': data.get('reply', '') or '',
        }
    except Exception as e:
        logger.debug("Gateway drafting unavailable or failed: %s", e)
        return None


def analyze_and_draft(
    comment_text: str,
    post_context: Optional[str] = None,
    tone: str = 'friendly',
    business_name: str = 'Our Business',
    business_type: str = 'restaurant',
    location: str = '',
) -> Dict[str, Any]:
    """
    Main interface for AI Reply Agent.
    Analyzes sentiment and produces an AI draft reply.
    """
    tone = (tone or 'friendly').lower()
    if tone not in TONES:
        tone = 'friendly'

    # Step 1: Rule-based sentiment analysis
    initial_sentiment = classify_sentiment(comment_text)

    # Step 2: Try the LLM gateway (task_type="content"); None -> fallback below.
    # source='gateway' on success: per-provider fallback happens inside the
    # gateway, so no single provider name is accurate here.
    llm_result = _call_gateway_llm(
        comment_text, initial_sentiment, tone, business_name, business_type, location, post_context
    )
    source = 'gateway' if llm_result else 'fallback'

    if llm_result and llm_result.get('reply'):
        final_sentiment = llm_result.get('sentiment', initial_sentiment)
        if final_sentiment not in SENTIMENTS:
            final_sentiment = initial_sentiment
        draft_reply = llm_result.get('reply', '')
    else:
        final_sentiment = initial_sentiment
        draft_reply = _get_fallback_reply(
            final_sentiment,
            tone=tone,
            business_name=business_name,
            business_type=business_type,
            location=location,
            post_context=post_context,
        )
        source = 'fallback'

    return {
        'sentiment': final_sentiment,
        'ai_draft_reply': draft_reply,
        'tone': tone,
        'confidence': 0.95 if source != 'fallback' else 0.85,
        'source': source,
    }
