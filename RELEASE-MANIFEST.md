# Colab MCP Adapter v0.1.0 Release Manifest

This manifest defines the intended source-control contents for the initial
`v0.1.0` release. It excludes `.git`, local virtual environments, caches,
bytecode, and build output.

## Repository release contents

```text
.gitignore
.python-version
LICENSE
PHASE-B-VERIFICATION.md
PHASE-C-VERIFICATION.md
PHASE-D-VERIFICATION.md
PHASE-E-VERIFICATION.md
PHASE-F-VERIFICATION.md
README.md
RELEASE-MANIFEST.md
RELEASE-READINESS.md
USAGE-PLAN.md
pyproject.toml
src/colab_mcp_adapter/__init__.py
src/colab_mcp_adapter/__main__.py
src/colab_mcp_adapter/adapter.py
src/colab_mcp_adapter/contracts.py
src/colab_mcp_adapter/parser.py
src/colab_mcp_adapter/server.py
tests/test_adapter.py
tests/test_stdio_protocol.py
uv.lock
```

## Distribution contents

The Hatchling source distribution is explicitly configured in `pyproject.toml`
to include the release license, README, lockfile, release documentation,
implementation source, and tests. The wheel contains the installable
`colab_mcp_adapter` package and its distribution metadata, including the MIT
license. Build verification must confirm the actual archive contents before
the release is considered ready.

## Version and entry point

- Package version: `0.1.0`
- Distribution name: `colab-mcp-adapter`
- Console entry point: `colab-mcp-adapter`
- Supported Python: `>=3.11`

## Release controls

- Keep the Colab MCP v0.1.0 implementation independent of compute federation.
- Do not include credentials, runtime data, or local environment files.
- The source manifest does not authorize commit, tag, push, or publication.
