# LLM Gateway

Provider-agnostic reasoning layer for Post-Pilot. Muse, OpenAI/Codex, Gemini,
and Claude are interchangeable behind one contract. Python implementation
(Flask project); a TypeScript port remains possible later without touching
skills, MCP, or core.

## Contract (`ai/providers/base.py`)

`LLMProvider` (`BaseAIProvider` is an alias) requires:

- `generate(prompt, system?) -> AIResponse`
- `stream(prompt, system?) -> Iterator[str]`
- `structured_output(prompt, schema, system?) -> dict`
- `tool_call(prompt, tools, system?) -> dict`
- `capabilities() -> [str]`
- `is_available() -> bool`

Concrete helpers inherited by all adapters: `health()` (cheap status snapshot,
no network) and `supports(capability)`. Per-request model selection: pass
`model=` to any generation call to override the adapter default.

Adapters are pure transports: prompts go out verbatim, no business logic, and
all LLM SDK imports are lazy (inside methods) so `import ai` never needs an
SDK installed. Verified by `tests/test_ai_gateway.py` (AST + `sys.modules`
checks).

## Adapters (`ai/providers/`)

| Name | Class | Transport | Key env |
|---|---|---|---|
| `Muse` | `MuseProvider` | Local HTTP endpoint (stdlib only) | `CLAUDE_API_URL`, `CLAUDE_API_KEY`, `CLAUDE_MODEL` |
| `openai` | `OpenAIProvider` | OpenAI SDK (lazy) | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| `gemini` | `GeminiProvider` | `google-genai` SDK (lazy) | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| `anthropic` | `ClaudeProvider` | `anthropic` SDK (lazy) | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |

Registry aliases (`ai/providers/__init__.py`): `Claude` -> `anthropic`,
`codex` -> `openai`. `load_provider(name)` resolves aliases; `KeyError` on
unknown names. `register_provider()` adds custom adapters.

`anthropic` and `google-genai` are optional dependencies (not in
`requirements.txt`); adapters fail cleanly with an install hint when missing.

## Routing (`ai/router.py` + `ai/context.py`)

Selection order per request: explicit `preferred_provider` -> task-type route
-> `default_provider` -> `fallback_order` -> any remaining provider; then
filtered by availability and required capabilities.

Default task routes (`DEFAULT_TASK_ROUTES`):

- `content`, `marketing` -> Muse, anthropic
- `structured`, `analysis` -> gemini
- `coding`, `dev`, `admin` -> openai

## Fallback (`ai/gateway.py`)

`AIGateway` tries candidates in router order and moves to the next provider on
any exception; raises only when all fail. `gateway.health()` snapshots every
provider; `gateway.explain(requirements)` previews routing (backs the
`provider.route` MCP tool).

## Config (env; see `.env.example`)

- `AI_DEFAULT_PROVIDER` (default `Muse`)
- `AI_FALLBACK_ORDER` (csv, e.g. `openai,gemini`)
- `AI_TASK_ROUTES` (JSON object, e.g. `{"content": ["gemini"]}`)
- Per-provider keys/models as in the table above

`GatewayConfig.from_env()` merges env over defaults; `build_gateway()` uses it
when no config is passed. No provider is ever required: any available subset
serves traffic.

## Flow

```text
caller -> AIGateway.generate(prompt, requirements?)
  -> AIRouter.candidates(requirements)   # pref -> task -> default -> fallback
  -> provider.generate(...)              # verbatim transport
  -> on error: next candidate            # fallback
  -> AIResponse(text, provider, model, usage)
```

## Known debt

- `anthropic` / `google-genai` SDKs are not installed in this environment;
  Gemini/Claude live paths are covered by fake-client tests only.
- `modules/ai_generator.py`, `modules/reply_agent.py`, and
  `modules/platform_adapter.py` are migrated (gateway, `task_type="content"`,
  deterministic fallbacks intact). No direct LLM SDK calls remain in
  generation paths.
- No retries/backoff inside adapters (fail fast so the gateway can fall back).
- No token-usage accounting or per-plan quota hooks yet.
