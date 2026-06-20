# PostPilot Pro — API Notes & Risk Register

> Read this before writing any platform integration code.
> Every gotcha documented here has burned someone before.

---

## ⚠️ Risk Register

| Platform | Risk | Severity | Mitigation |
|----------|------|----------|------------|
| TikTok | Content Posting API requires formal app approval (5–10 days, can be rejected) | 🔴 High | Ship script generator now; auto-upload activates post-approval. Never block launch on this. |
| Google Business | Requires verified GMB listing. Unverified users fully blocked. | 🔴 High | Detect on connect. Show verification guide. Mark as "pending" if unverified. |
| YouTube | 10,000 unit quota/day. 1 upload = 1,600 units = ~6 uploads/day | 🔴 High | Each user authenticates with their own Google account (own quota). Never share one key across users. |
| Facebook | Page token expires every 60 days | 🟡 Medium | Weekly background expiry check. Red pill at 7 days. One-click reauth. |
| Google OAuth | Access token expires every 1 hour | 🟡 Medium | Store refresh_token. Auto-refresh silently before every API call. |
| TikTok OAuth | Token expires every 24 hours | 🔴 High | Daily background refresh job. Alert user if refresh fails. |
| Instagram | 25 posts per 24 hours max | 🟢 Low | Rate limit tracker per user. Queue overflow to next day. |
| Meta API versions | Graph API deprecates old versions | 🟡 Medium | Pin to v19.0. Subscribe to Meta developer changelog. |
| Account bans | User account flagged for spam | 🟢 Low | Never exceed platform limits. Human approval for bulk posts. |

---

## Facebook (Graph API v19.0)

### Endpoints
```
Text post:   POST /{page-id}/feed          params: message
Photo post:  POST /{page-id}/photos        params: url, caption
Video post:  POST /{page-id}/videos        params: file_url, description
Schedule:    Add published=false + scheduled_publish_time (Unix timestamp)
```

### Gotchas
- Always use PAGE token, not user token
- Token expires ~60 days. Store long-lived version.
- Rate limit: 200 calls/hour per page token
- Scheduled time must be 10+ minutes in the future
- Videos must be publicly accessible HTTPS URL
- No shortened URLs (bit.ly etc) — often rejected

### Permissions
- `pages_manage_posts`
- `pages_read_engagement`
- `publish_video`

---

## Instagram (Graph API v19.0)

### Endpoints
```
Create container: POST /{ig-id}/media
Publish:          POST /{ig-id}/media_publish
```

### Gotchas
- TWO-STEP ALWAYS: create container first, then publish
- IMAGE IS REQUIRED. No text-only posts.
- Image must be public HTTPS URL (not localhost during dev)
- JPEG only for photos. MP4 for Reels.
- Preferred dimensions: 1080×1350 (4:5) or 1080×1080 (square)
- Reels: 3–60 seconds, MP4, H.264 codec
- Rate limit: 25 posts per 24 hours
- Business/Creator account required

### Permissions
- `instagram_basic`
- `instagram_content_publish`
- `pages_read_engagement`

---

## Google Business Profile API

### Endpoints
```
List accounts:  GET  /v1/accounts
List locations: GET  /v1/{account}/locations
Create post:    POST /v4/{location}/localPosts
Get insights:   GET  /v4/{location}/localPosts/{post}/insights
```

### Gotchas
- VERIFICATION REQUIRED. Unverified listings cannot post.
- Posts expire after 7 days (standard). Events last until event date.
- ASCII-safe text only. Emojis and special chars often rejected.
- Max 1500 characters per post
- No hashtags (Google doesn't use them)
- Image upload separate from post creation
- Rate limit: 500 QPM
- Access token expires in 1 HOUR — always use refresh_token

### Setup Requirements
- Google Cloud project with Business Profile API enabled
- Verified Google Business listing
- OAuth 2.0 Web Application credentials
- Scope: `https://www.googleapis.com/auth/business.manage`

---

## YouTube (Data API v3)

### Endpoints
```
Upload video:   POST /upload/youtube/v3/videos (resumable)
Update video:   PUT  /youtube/v3/videos
Get channel:    GET  /youtube/v3/channels
```

### Gotchas
- Quota: 10,000 units/day. Upload = 1,600 units. Only ~6 uploads/day.
- EACH USER must use their own Google OAuth (own quota)
- Resumable upload required for files >5MB
- Two-step: initiate upload URL, then stream video to it
- Video enters "processing" state first — async workflow
- Title max: 100 chars. Description max: 5000 chars.
- Quota resets at midnight Pacific Time
- Same OAuth token as Google Business (just add YouTube scope)

### Scope
- `https://www.googleapis.com/auth/youtube.upload`

---

## TikTok (Content Posting API v2)

### Endpoints
```
Init upload:    POST /v2/post/publish/video/init/
Check status:   GET  /v2/post/publish/status/fetch/
```

### Gotchas
- Requires APPROVED developer app — not instant
- App must be approved for `video.upload` and `video.publish` scopes
- Videos: 3–60 seconds
- Pull-from-URL method available (`source: PULL_FROM_URL`)
- Token expires in 24 HOURS — daily refresh required
- Privacy levels: `PUBLIC_TO_EVERYONE`, `MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY`
- Title max: 150 characters
- Rate limit: 100 posts/day per user
- App review: 5–10 business days, requires Privacy Policy + ToS URL

---

## Website (Internal — No External API)

### How It Works
```
Dashboard push → writes banner.json → embed.js fetches it → user's website updates
```

### Schema (banner.json)
```json
{
  "banner":   { "message": "", "link": "", "active": true },
  "specials": { "items": [], "updated": "" },
  "hours":    { "text": "", "exceptions": [] },
  "location": { "text": "", "lat": null, "lng": null },
  "gallery":  { "images": [] },
  "events":   { "upcoming": [] }
}
```

### Important
- Add `Access-Control-Allow-Origin: *` header to banner.json and embed.js routes
- Cache-busting: `?t=timestamp` already implemented
- Never put tokens or sensitive data in banner.json — it's publicly readable
- Version embed.js carefully — existing installs must not break on updates
