# Post-Pilot MCP Server

This MCP server exposes Post-Pilot's audit and fix tools to any MCP-compatible
client: Claude Desktop, Cursor, Windsurf, or a hosted HTTP endpoint.

The Flask GUI (`app.py`) and this MCP server are **independent interfaces into
the same codebase** — running one does not affect the other.

---

## Tools Available

| Tool | What it does |
|---|---|
| `get_repo_structure` | List files/dirs in any GitHub repo |
| `read_file` | Read any file from the repo |
| `audit_repo` | Automated checklist: CI, tests, db.py, plan_guard, scheduler, etc. |
| `write_file` | Create or update any file (auto-fetches SHA so no mismatch errors) |
| `list_open_issues` | List open GitHub issues, optionally filtered by label |
| `create_issue` | Create a GitHub issue from an audit finding |
| `list_recent_commits` | Verify fix commits landed on any branch |

### Post-Pilot product tools (registered by the same server)

| Tool | Permission | What it does |
|---|---|---|
| `business_get_tool` | read | Business profile for a user |
| `menu_get_tool` | read | Website menu section |
| `specials_list_tool` | read | Daily specials, optional status filter |
| `events_list_tool` | read | Events, optional status filter |
| `content_generate_tool` | write | Master + per-platform captions (plan quota) |
| `content_schedule_tool` | write | Schedule a post via PostScheduler |
| `post_publish_tool` | publish | Publish NOW to connected platforms |
| `analytics_get_tool` | read | Combined FB+IG analytics summary |
| `inbox_reply_tool` | write | Draft a reply (DRAFT ONLY, never auto-posts) |

Auth model: every tool takes an explicit `user_id` and is scoped to that
user (owner/team only); secrets are never returned. Each tool's SPEC dict
in `mcp/tools/` documents its permission and auth notes. Because the PyPI
`mcp` SDK shadows the local `mcp/` directory, importers must call
`modules.mcp_bootstrap.ensure_local_mcp_tools()` before `mcp.tools.*`
imports (server.py already does this).

---

## Setup

### 1. Install dependencies

```bash
pip install mcp PyGithub
```

### 2. Create a GitHub Fine-Grained Personal Access Token

Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**

Grant it (scoped to `Post-Pilot` repo only):
- **Contents**: Read & Write
- **Issues**: Read & Write
- **Metadata**: Read-only

### 3. Set the environment variable

```bash
export GITHUB_TOKEN=your_token_here
```

---

## Run Locally — Claude Desktop / Cursor (stdio)

```bash
python mcp/server.py
```

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "post-pilot": {
      "command": "python",
      "args": ["/absolute/path/to/Post-Pilot/mcp/server.py"],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

Restart Claude Desktop — **post-pilot** will appear in the tools list.

### Cursor

Add `.cursor/mcp.json` to your project root:

```json
{
  "mcpServers": {
    "post-pilot": {
      "command": "python",
      "args": ["mcp/server.py"],
      "env": {
        "GITHUB_TOKEN": "your_token_here"
      }
    }
  }
}
```

---

## Run as HTTP Server (hosted / shareable)

```bash
python mcp/server.py --transport sse --port 8001
```

Point any MCP client at `http://your-host:8001/sse`.

### Deploy on Railway alongside the Flask app

Add a second Railway service pointing to the same repo with start command:

```
python mcp/server.py --transport sse --port 8001
```

Set `GITHUB_TOKEN` as a Railway environment variable (never in code).

---

## Example Prompts Once Connected

> *"Audit the ShadowWalkerNC/Post-Pilot repo and tell me what's missing"*

> *"Read modules/app.py and check if init_scheduler is wired in"*

> *"Create a GitHub issue for the missing Railway Postgres step"*

> *"Show me the last 5 commits on main"*

---

## Project Structure

```
Post-Pilot/
├── app.py              ← Flask GUI (unchanged)
├── modules/            ← shared business logic (+ mcp_bootstrap.py)
├── skills/             ← provider-agnostic prompt packs + loader.py
├── integrations/culinaryos/ ← adapter-only CulinaryOS client + contract
├── mcp/
│   ├── server.py       ← MCP server (audit + product tools)
│   ├── tools/          ← product tools (business, specials, events,
│   │                     content, publish, analytics, inbox)
│   └── README.md       ← you are here
├── tests/              ← pytest suite (+ test_skills_loader, test_mcp_tools)
└── requirements.txt    ← includes: mcp, PyGithub
```
