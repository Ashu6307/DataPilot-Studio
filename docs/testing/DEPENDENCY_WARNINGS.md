# Dependency Warnings

## Starlette TestClient deprecation

The Python suite currently emits one test-only warning from FastAPI's re-exported `TestClient`: Starlette reports that the installed `httpx` integration is deprecated in favour of the future `httpx2` package.

- Runtime impact: none; production request handling does not import `TestClient`.
- Test impact: none observed; API tests pass.
- Security impact: no known vulnerability is indicated by this warning, and `npm audit --audit-level=high` is a separate gate.
- Decision: do not perform a blind major dependency change. Upgrade FastAPI/Starlette and their supported HTTP client together when an upstream-compatible release path is available, then remove this note after the suite is warning-free.
