"""
server.py -- Post-Pilot MCP Server

Exposes audit and fix tools for use in Claude Desktop, Cursor, Windsurf,
or any MCP-compatible client.

Setup:
    pip install mcp PyGithub
    export GITHUB_TOKEN=your_personal_access_token

Run (stdio, for Claude Desktop / Cursor):
    python mcp/server.py

Run (HTTP, for hosted/shared use):
    python mcp/server.py --transport sse --port 8001

Add to Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "post-pilot": {
          "command": "python",
          "args": ["/absolute/path/to/Post-Pilot/mcp/server.py"],
          "env": { "GITHUB_TOKEN": "your_token_here" }
        }
      }
    }
"""

import os
import sys
import logging
from datetime import datetime

# Ensure repo root is on the path so we can import modules/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:  # mcp>=2 renamed FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as _MCPServerBase
except ImportError:  # mcp<2
    from mcp.server.fastmcp import FastMCP as _MCPServerBase
from github import Github, GithubException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('postpilot-mcp')

mcp = _MCPServerBase(
    name='post-pilot',
    description='Audit and fix tools for the Post-Pilot social media SaaS repo.',
)


def _gh(owner: str, repo: str):
    """Return an authenticated PyGithub repo object."""
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise RuntimeError('GITHUB_TOKEN environment variable not set.')
    return Github(token).get_repo(f'{owner}/{repo}')


# ---------------------------------------------------------------------------
# Tool 1: Repo structure snapshot
# ---------------------------------------------------------------------------
@mcp.tool()
def get_repo_structure(owner: str, repo: str) -> dict:
    """
    Return a top-level file/directory listing for a GitHub repo.
    Use this before running an audit to confirm the repo layout.
    """
    r = _gh(owner, repo)
    contents = r.get_contents('')
    return {
        'repo':  f'{owner}/{repo}',
        'files': [
            {'name': c.name, 'type': c.type, 'size': c.size}
            for c in contents
        ],
    }


# ---------------------------------------------------------------------------
# Tool 2: Read any file
# ---------------------------------------------------------------------------
@mcp.tool()
def read_file(owner: str, repo: str, path: str) -> dict:
    """
    Read the contents of any file in the repo.
    Use this to inspect code before suggesting or applying fixes.
    """
    r    = _gh(owner, repo)
    file = r.get_contents(path)
    return {
        'path':    path,
        'sha':     file.sha,
        'content': file.decoded_content.decode('utf-8', errors='replace'),
    }


# ---------------------------------------------------------------------------
# Tool 3: Audit checklist
# ---------------------------------------------------------------------------
@mcp.tool()
def audit_repo(owner: str, repo: str) -> dict:
    """
    Run a lightweight automated audit of the repo.
    Checks for: test directory, CI pipeline, requirements completeness,
    db.py abstraction, plan_guard, scheduler_worker, TODO.md.
    Returns a checklist with pass/fail per item.
    """
    r       = _gh(owner, repo)
    results = {}

    checks = [
        ('tests/ directory',    'tests'),
        ('CI pipeline',         '.github/workflows/ci.yml'),
        ('db.py abstraction',   'modules/db.py'),
        ('plan_guard.py',       'modules/plan_guard.py'),
        ('scheduler_worker.py', 'modules/scheduler_worker.py'),
        ('TODO.md',             'TODO.md'),
        ('requirements.txt',    'requirements.txt'),
    ]

    for label, path in checks:
        try:
            r.get_contents(path)
            results[label] = 'PASS'
        except GithubException:
            results[label] = 'MISSING'

    # Check requirements for key packages
    try:
        req_text = r.get_contents('requirements.txt').decoded_content.decode()
        for pkg in ['psycopg2', 'APScheduler', 'pytest', 'sentry-sdk']:
            results[f'requirements: {pkg}'] = 'PASS' if pkg in req_text else 'MISSING'
    except GithubException:
        results['requirements.txt'] = 'MISSING'

    passed = sum(1 for v in results.values() if v == 'PASS')
    total  = len(results)

    return {
        'repo':    f'{owner}/{repo}',
        'audited': datetime.utcnow().isoformat() + 'Z',
        'score':   f'{passed}/{total}',
        'checks':  results,
    }


# ---------------------------------------------------------------------------
# Tool 4: Write / update a single file
# ---------------------------------------------------------------------------
@mcp.tool()
def write_file(owner: str, repo: str, path: str, content: str, commit_message: str) -> dict:
    """
    Create or update a single file in the repo.
    Automatically fetches the current SHA if the file already exists.
    Use this to apply targeted fixes.
    """
    r   = _gh(owner, repo)
    sha = None
    try:
        sha = r.get_contents(path).sha
    except GithubException:
        pass  # new file

    if sha:
        result = r.update_file(path, commit_message, content, sha)
    else:
        result = r.create_file(path, commit_message, content)

    return {
        'path':       path,
        'commit_sha': result['commit'].sha,
        'html_url':   result['commit'].html_url,
    }


# ---------------------------------------------------------------------------
# Tool 5: List open issues
# ---------------------------------------------------------------------------
@mcp.tool()
def list_open_issues(owner: str, repo: str, label: str = None) -> list:
    """
    List open GitHub issues, optionally filtered by label.
    Useful for cross-referencing audit findings with existing tickets.
    """
    r      = _gh(owner, repo)
    kwargs = {'state': 'open'}
    if label:
        kwargs['labels'] = [label]
    issues = r.get_issues(**kwargs)
    return [
        {
            'number': i.number,
            'title':  i.title,
            'url':    i.html_url,
            'labels': [l.name for l in i.labels],
        }
        for i in list(issues)[:25]
    ]


# ---------------------------------------------------------------------------
# Tool 6: Create a GitHub issue from an audit finding
# ---------------------------------------------------------------------------
@mcp.tool()
def create_issue(owner: str, repo: str, title: str, body: str, labels: list = None) -> dict:
    """
    Create a GitHub issue. Use this to track audit findings that
    need manual attention (e.g. Railway Postgres setup).
    """
    r     = _gh(owner, repo)
    issue = r.create_issue(
        title=title,
        body=body,
        labels=labels or [],
    )
    return {
        'number':   issue.number,
        'title':    issue.title,
        'html_url': issue.html_url,
    }


# ---------------------------------------------------------------------------
# Tool 7: List recent commits
# ---------------------------------------------------------------------------
@mcp.tool()
def list_recent_commits(owner: str, repo: str, branch: str = 'main', limit: int = 10) -> list:
    """
    Return the N most recent commits on a branch.
    Use this to verify that fix commits landed correctly.
    """
    r       = _gh(owner, repo)
    commits = r.get_commits(sha=branch)
    return [
        {
            'sha':     c.sha[:7],
            'message': c.commit.message.splitlines()[0],
            'author':  c.commit.author.name,
            'date':    c.commit.author.date.isoformat(),
            'url':     c.html_url,
        }
        for c in list(commits)[:limit]
    ]


# ---------------------------------------------------------------------------
# Post-Pilot product tools (delegate to mcp/tools/*, which delegate to modules/)
# ---------------------------------------------------------------------------
import modules.mcp_bootstrap  # local mcp/tools is shadowed by the PyPI mcp SDK
modules.mcp_bootstrap.ensure_local_mcp_tools()
from mcp.tools.business import (
    business_get, business_update, menu_get, menu_list, menu_item_get,
)
from mcp.tools.specials import specials_list, specials_get
from mcp.tools.events import events_list, events_get
from mcp.tools.hours import hours_get
from mcp.tools.content import (
    content_generate, content_schedule, content_adapt, content_preview,
)
from mcp.tools.publish import post_publish, post_cancel, post_status
from mcp.tools.analytics import (
    analytics_get, analytics_top_posts, analytics_performance_summary,
)
from mcp.tools.inbox import inbox_reply, inbox_list, inbox_approve_reply, inbox_skip
from mcp.tools.media import media_list, media_get
from mcp.tools.brand import brand_get, brand_validate
from mcp.tools.automation import automation_run, automation_status
from mcp.tools.provider import provider_list, provider_route, provider_health


@mcp.tool()
def business_get_tool(user_id: str) -> dict:
    """[read] Get the business profile for a user. Scoped to user_id; owner/team only."""
    return business_get(user_id)


@mcp.tool()
def menu_get_tool(user_id: str) -> dict:
    """[read] Get the website menu section for a user. Scoped to user_id; owner/team only."""
    return menu_get(user_id)


@mcp.tool()
def specials_list_tool(user_id: str, status: str = None, limit: int = 25) -> list:
    """[read] List daily specials for a user, optionally filtered by status."""
    return specials_list(user_id, status=status, limit=limit)


@mcp.tool()
def events_list_tool(user_id: str, status: str = None, limit: int = 25) -> list:
    """[read] List events for a user, optionally filtered by status."""
    return events_list(user_id, status=status, limit=limit)


@mcp.tool()
def content_generate_tool(
    user_id: str,
    content_type: str = 'general',
    tone: str = 'friendly',
    keywords: list = None,
    platforms: list = None,
    special: str = '',
) -> dict:
    """[write] Generate master + per-platform captions. Consumes plan AI quota."""
    return content_generate(user_id, content_type, tone, keywords, platforms, special)


@mcp.tool()
def content_schedule_tool(
    user_id: str,
    caption: str,
    scheduled_at: str,
    platforms: list = None,
    content_type: str = 'general',
    image_url: str = None,
) -> dict:
    """[write] Schedule a post for future publishing. Owner/team only."""
    return content_schedule(user_id, caption, scheduled_at, platforms, content_type, image_url)


@mcp.tool()
def post_publish_tool(
    user_id: str,
    caption: str = None,
    content_type: str = 'general',
    platforms: list = None,
    image_url: str = None,
    video_url: str = None,
    link_url: str = None,
) -> dict:
    """[publish] Publish NOW to connected platforms. Requires publish rights."""
    return post_publish(user_id, caption, None, content_type, platforms, image_url, video_url, link_url)


@mcp.tool()
def analytics_get_tool(user_id: str, days: int = 30) -> dict:
    """[read] Combined FB+IG analytics summary. Tokens stay server-side."""
    return analytics_get(user_id, days)


@mcp.tool()
def inbox_reply_tool(
    comment_text: str,
    user_id: str = None,
    post_context: str = None,
    tone: str = 'friendly',
) -> dict:
    """[write] Draft an on-brand reply. DRAFT ONLY - never auto-posts."""
    return inbox_reply(comment_text, user_id, post_context, tone)


@mcp.tool()
def business_update_tool(user_id: str, updates: dict) -> dict:
    """[write] Update business profile fields. Owner/team only."""
    return business_update(user_id, updates)


@mcp.tool()
def menu_list_tool(user_id: str, search: str = None, limit: int = 25) -> list:
    """[read] List menu items, optionally filtered by search text."""
    return menu_list(user_id, search=search, limit=limit)


@mcp.tool()
def menu_item_get_tool(user_id: str, item: str) -> dict:
    """[read] Get one menu item by id or name."""
    return menu_item_get(user_id, item)


@mcp.tool()
def specials_get_tool(user_id: str, special_id: int) -> dict:
    """[read] Get one special by id."""
    return specials_get(user_id, special_id)


@mcp.tool()
def events_get_tool(user_id: str, event_id: int) -> dict:
    """[read] Get one event by id."""
    return events_get(user_id, event_id)


@mcp.tool()
def hours_get_tool(user_id: str, status: str = None, limit: int = 25) -> list:
    """[read] List hours overrides / closures, upcoming first."""
    return hours_get(user_id, status=status, limit=limit)


@mcp.tool()
def content_adapt_tool(
    user_id: str, master: str, platforms: list, tone: str = 'friendly'
) -> dict:
    """[write] Adapt a master caption for platforms. Consumes plan AI quota."""
    return content_adapt(user_id, master, platforms, tone)


@mcp.tool()
def content_preview_tool(
    user_id: str, master: str, platforms: list,
    tone: str = 'friendly', image_url: str = None,
) -> dict:
    """[read] Preview adapted captions with char counts and media warnings."""
    return content_preview(user_id, master, platforms, tone, image_url)


@mcp.tool()
def post_cancel_tool(user_id: str, job_id: str) -> dict:
    """[write] Cancel a scheduled job by id."""
    return post_cancel(user_id, job_id)


@mcp.tool()
def post_status_tool(user_id: str, job_id: str) -> dict:
    """[read] Check whether a scheduled job id is still pending."""
    return post_status(user_id, job_id)


@mcp.tool()
def analytics_top_posts_tool(
    user_id: str, days: int = 30, limit: int = 5, metric: str = 'engaged'
) -> dict:
    """[read] Top posts ranked by engaged, reach, or likes."""
    return analytics_top_posts(user_id, days=days, limit=limit, metric=metric)


@mcp.tool()
def analytics_performance_summary_tool(user_id: str, days: int = 30) -> dict:
    """[read] Compact KPI summary for a user."""
    return analytics_performance_summary(user_id, days=days)


@mcp.tool()
def inbox_list_tool(
    user_id: str, status: str = None, sentiment: str = None,
    platform: str = None, limit: int = 50,
) -> dict:
    """[read] List ingested social comments with optional filters."""
    return inbox_list(user_id, status=status, sentiment=sentiment,
                      platform=platform, limit=limit)


@mcp.tool()
def inbox_approve_reply_tool(
    user_id: str, item_id: int, reply_text: str = None
) -> dict:
    """[publish] Approve and POST a reply (defaults to AI draft). Publishes live."""
    return inbox_approve_reply(user_id, item_id, reply_text)


@mcp.tool()
def inbox_skip_tool(user_id: str, item_id: int) -> dict:
    """[write] Mark an inbox item skipped (no reply posted)."""
    return inbox_skip(user_id, item_id)


@mcp.tool()
def media_list_tool(user_id: str, limit: int = 25) -> list:
    """[read] List media attachments from post history."""
    return media_list(user_id, limit=limit)


@mcp.tool()
def media_get_tool(user_id: str, media_id: int) -> dict:
    """[read] Get one post-history media row by id."""
    return media_get(user_id, media_id)


@mcp.tool()
def brand_get_tool(user_id: str) -> dict:
    """[read] Get brand voice fields for a user."""
    return brand_get(user_id)


@mcp.tool()
def brand_validate_tool(user_id: str, text: str) -> dict:
    """[read] Deterministic brand check on a text (v1, no LLM)."""
    return brand_validate(user_id, text)


@mcp.tool()
def automation_run_tool(user_id: str) -> dict:
    """[write] Run the content automation agent now for one user."""
    return automation_run(user_id)


@mcp.tool()
def automation_status_tool(user_id: str, limit: int = 25) -> list:
    """[read] Recent automation audit rows for a user."""
    return automation_status(user_id, limit=limit)


@mcp.tool()
def provider_list_tool() -> dict:
    """[read] List LLM providers with availability and capabilities. No keys."""
    return provider_list()


@mcp.tool()
def provider_route_tool(
    task_type: str = None, preferred_provider: str = None, capabilities: list = None
) -> dict:
    """[read] Preview which provider would serve a request (no generation)."""
    return provider_route(task_type, preferred_provider, capabilities)


@mcp.tool()
def provider_health_tool(name: str = None) -> dict:
    """[read] Health snapshot for one provider, or all when omitted. No keys."""
    return provider_health(name)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--transport', default='stdio', choices=['stdio', 'sse'])
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()

    if args.transport == 'sse':
        mcp.run(transport='sse', port=args.port)
    else:
        mcp.run(transport='stdio')
