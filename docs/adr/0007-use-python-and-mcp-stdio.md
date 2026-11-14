# ADR-0007: Use Python and the official MCP SDK over stdio

## Status

Accepted by Kevin Ceciliano Gamboa in response to Q25. Exact dependency pins and client compatibility remain implementation verification work.

## Date

2026-11-13

## Context

The product is a local server with typed repair operations, a human CLI and two evaluation layers. Python matches the author's experience and provides the data, testing and protocol libraries required for this scope. A complete demonstration must run without deploying a network service.

## Options Considered

1. **Python and the official MCP SDK over stdio.** Integrates with the proposed data stack and local subprocess clients; requires careful process, logging and compatibility tests.
2. **TypeScript and an MCP SDK.** Provides a strong tool ecosystem, but would separate the primary implementation from the chosen Python data libraries or require a different data stack.
3. **HTTP transport from the first version.** Supports a separately deployed service, but adds network lifecycle and authorization concerns without an accepted remote-use requirement.

## Decision

We choose Python, the official MCP Python SDK and stdio as the initial transport. The client launches the server as a subprocess. Protocol messages use stdout; application logs use stderr. No initial HTTP service or second transport is required.

Keep repair semantics and persistence independent of SDK handlers so the CLI, deterministic tests and real-agent harness exercise the same domain behavior. Tools expose typed input and output contracts; MCP errors must distinguish domain/tool failures from protocol failures.

Use a project-owned environment rather than installing into the host's existing Python environment. Pin and lock published dependencies; do not build against an unpinned main branch or combine examples from incompatible SDK major versions.

## Consequences

- CI must start the actual stdio subprocess, discover tools, validate structured outputs and test failure responses.
- Supported client/protocol versions must be listed from measured compatibility, not inferred from the selected SDK.
- The CLI and server share domain services but expose different capabilities; SDK registration must not accidentally expose human approval commands.
- Runtime and dependency updates require rerunning protocol and data-fidelity checks.
- The initial package/runtime pins are documented in the technical specification as a candidate baseline until installation and compatibility are verified.

## Related Decisions

- [ADR-0004](0004-expose-six-mcp-tools.md): tool responsibilities.
- [ADR-0005](0005-evaluate-server-and-real-agent.md): protocol and agent evaluations.
- [ADR-0008](0008-use-sqlite-and-pyarrow.md): storage and interchange libraries.

## References

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio).
- [SDK structured output](https://py.sdk.modelcontextprotocol.io/servers/structured-output/).
