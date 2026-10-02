"""
modules/mcp_bootstrap.py — import helper for Post-Pilot's local MCP tools.

Problem: the PyPI `mcp` SDK (a regular package, required by mcp/server.py)
shadows the repo-local `mcp/` directory, so `import mcp.tools` resolves to
the SDK and fails. The local dir deliberately has no `__init__.py` so that
`python mcp/server.py` keeps importing the SDK in script mode.

Solution: `ensure_local_mcp_tools()` path-loads `mcp/tools/*.py` into
`sys.modules` under their canonical `mcp.tools.*` names. `from`/`import`
statements check `sys.modules` first, so after one bootstrap call every
`from mcp.tools.<x> import ...` statement (tests, server.py, and the tool
modules' own cross-imports) resolves to the local files.

Usage (must run before any mcp.tools import):
    import modules.mcp_bootstrap
    modules.mcp_bootstrap.ensure_local_mcp_tools()
    from mcp.tools import TOOL_SPECS  # now resolves locally
"""

import importlib.util
import os
import sys


def ensure_local_mcp_tools() -> str:
    """Make `mcp.tools.*` importable. Returns 'native' or 'path-loaded'."""
    if 'mcp.tools' in sys.modules:
        return 'cached'
    try:
        import mcp.tools  # noqa: F401 — works when the SDK doesn't shadow
        return 'native'
    except ImportError:
        pass

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools_dir = os.path.join(repo_root, 'mcp', 'tools')
    init_file = os.path.join(tools_dir, '__init__.py')
    if not os.path.isfile(init_file):
        raise ImportError(f'Local MCP tools not found at {tools_dir}')

    # Ensure a parent `mcp` entry exists (SDK or stub) for submodule imports.
    try:
        import mcp  # noqa: F401
    except ImportError:
        import types
        stub = types.ModuleType('mcp')
        stub.__path__ = [os.path.join(repo_root, 'mcp')]
        sys.modules['mcp'] = stub

    spec = importlib.util.spec_from_file_location(
        'mcp.tools', init_file, submodule_search_locations=[tools_dir]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load local MCP tools from {init_file}')
    module = importlib.util.module_from_spec(spec)
    sys.modules['mcp.tools'] = module  # register before exec for cross-imports
    spec.loader.exec_module(module)
    return 'path-loaded'
