# brand_guard rules (hard fails)

1. **Banned words** — any `banned_words` hit is an automatic FAIL.
2. **Invented offers** — "free", "% off", "giveaway", "sold out" fail unless
   the source data confirms them.
3. **Platform limits** — X/Twitter ≤280 chars; Google Business: no hashtags;
   Instagram hook ≤125 chars; website banner ≤120 chars.
4. **Tone break** — urgent/hype language in a `friendly`/`community` brand
   fails; profanity or snark always fails.
5. **Missing CTA** — fails when `required_cta` is true and no visit/order/
   call/DM action is present.
