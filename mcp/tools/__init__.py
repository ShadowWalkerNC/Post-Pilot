"""
mcp/tools — Post-Pilot product tools for MCP clients.

Each tool module delegates to an existing service in modules/ (no new
business logic here) and exposes a SPEC dict documenting the permission
model. Auth model for all tools:

- MCP transport auth: the hosting layer (Claude Desktop local process or
  SSE endpoint behind the operator's auth proxy) authenticates the *caller*.
- user_id scoping: every user-data tool takes an explicit user_id and only
  touches that user's rows/tokens. There is no cross-tenant access.
- Write/publish tools require the caller to be the account owner or a team
  member with the matching role; enforcement happens in the underlying
  service / plan_guard layer.
- Secrets (OAuth tokens, API keys) are never returned by any tool.
"""

from mcp.tools.business import (
    SPEC_BUSINESS_GET, SPEC_BUSINESS_UPDATE, SPEC_MENU_GET,
    SPEC_MENU_LIST, SPEC_MENU_ITEM_GET,
)
from mcp.tools.specials import SPEC_SPECIALS_LIST, SPEC_SPECIALS_GET
from mcp.tools.events import SPEC_EVENTS_LIST, SPEC_EVENTS_GET
from mcp.tools.hours import SPEC_HOURS_GET
from mcp.tools.content import (
    SPEC_CONTENT_GENERATE, SPEC_CONTENT_SCHEDULE,
    SPEC_CONTENT_ADAPT, SPEC_CONTENT_PREVIEW,
)
from mcp.tools.publish import SPEC_POST_PUBLISH, SPEC_POST_CANCEL, SPEC_POST_STATUS
from mcp.tools.analytics import (
    SPEC_ANALYTICS_GET, SPEC_ANALYTICS_TOP_POSTS,
    SPEC_ANALYTICS_PERFORMANCE_SUMMARY,
)
from mcp.tools.inbox import (
    SPEC_INBOX_LIST, SPEC_INBOX_REPLY,
    SPEC_INBOX_APPROVE_REPLY, SPEC_INBOX_SKIP,
)
from mcp.tools.media import SPEC_MEDIA_LIST, SPEC_MEDIA_GET
from mcp.tools.brand import SPEC_BRAND_GET, SPEC_BRAND_VALIDATE
from mcp.tools.automation import SPEC_AUTOMATION_RUN, SPEC_AUTOMATION_STATUS
from mcp.tools.provider import (
    SPEC_PROVIDER_LIST, SPEC_PROVIDER_ROUTE, SPEC_PROVIDER_HEALTH,
)

TOOL_SPECS = [
    SPEC_BUSINESS_GET,
    SPEC_BUSINESS_UPDATE,
    SPEC_MENU_GET,
    SPEC_MENU_LIST,
    SPEC_MENU_ITEM_GET,
    SPEC_SPECIALS_LIST,
    SPEC_SPECIALS_GET,
    SPEC_EVENTS_LIST,
    SPEC_EVENTS_GET,
    SPEC_HOURS_GET,
    SPEC_CONTENT_GENERATE,
    SPEC_CONTENT_ADAPT,
    SPEC_CONTENT_SCHEDULE,
    SPEC_CONTENT_PREVIEW,
    SPEC_POST_PUBLISH,
    SPEC_POST_CANCEL,
    SPEC_POST_STATUS,
    SPEC_ANALYTICS_GET,
    SPEC_ANALYTICS_TOP_POSTS,
    SPEC_ANALYTICS_PERFORMANCE_SUMMARY,
    SPEC_INBOX_LIST,
    SPEC_INBOX_REPLY,
    SPEC_INBOX_APPROVE_REPLY,
    SPEC_INBOX_SKIP,
    SPEC_MEDIA_LIST,
    SPEC_MEDIA_GET,
    SPEC_BRAND_GET,
    SPEC_BRAND_VALIDATE,
    SPEC_AUTOMATION_RUN,
    SPEC_AUTOMATION_STATUS,
    SPEC_PROVIDER_LIST,
    SPEC_PROVIDER_ROUTE,
    SPEC_PROVIDER_HEALTH,
]

TOOL_NAMES = [spec['name'] for spec in TOOL_SPECS]


def get_tool_spec(name: str) -> dict:
    """Return the SPEC dict for a tool name. Raises KeyError if unknown."""
    for spec in TOOL_SPECS:
        if spec['name'] == name:
            return spec
    raise KeyError(f'Unknown MCP tool: {name}')
