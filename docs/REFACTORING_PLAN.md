# Refactoring Roadmap

## Objective

Improve maintainability without destabilizing Windows desktop automation or silently changing public behavior. Refactoring is staged: keep main stable, isolate changes on feature branches, and preserve compatibility shims until callers and tests have migrated.

## Current baseline

- ai_controller.py is the public Python controller facade.
- agent_server.py is the current FastAPI entry point and owns route definitions, request schemas, authentication, host validation, and desktop integration.
- api_client.py is the Python HTTP client.
- Eyes/, Hands/, Context/, and Planner/ contain the primary perception, input, context, and planning capabilities.
- action_orchestrator.py, action_verifier.py, and action_recovery.py implement the action lifecycle.
- workflow_runner.py and Planner/goal_executor.py represent distinct workflow execution paths that need an explicit boundary before any consolidation.

## Target boundaries

    src/desktop_agent/
      config/       validated settings and model configuration
      api/
        routes/     FastAPI routers grouped by capability
        schemas/    request/response contracts
        dependencies.py
        errors.py
      application/  use cases and orchestration
      domain/       action, goal, verification, and policy types
      perception/   observation interfaces and shared schemas
      adapters/
        windows/    UIA, Win32, mouse, keyboard
        vision/     OCR, CV, visual grounding
        models/     local/cloud model providers
      persistence/  checkpoints and task state
      client/       reusable HTTP client
    tests/
    docs/

This is a target, not a claim that the whole codebase has already been moved. Existing top-level imports should remain as compatibility shims until downstream callers are migrated.

## Migration phases

### Phase 1 — Configuration and baseline contracts
- Centralize host, port, API URL, CORS, allowed-host, and model settings.
- Provide .env.example; never commit secrets.
- Add tests for settings validation and defaults.
- Record current public entry points and execution paths.

### Phase 2 — API boundary
- Split route handlers into api/routes/eyes.py, hands.py, context.py, and health.py.
- Move request/response models into api/schemas/.
- Move authentication, host validation, and common exception translation into dependencies/middleware modules.
- Keep agent_server:app and run_server() as compatibility exports.
- Add API contract tests before changing route behavior.

### Phase 3 — Application and domain logic
- Keep route handlers thin: validate input, call a use case, serialize a result.
- Move orchestration, planning, verification, recovery, and policy decisions out of UI/API modules.
- Define one documented action/result contract across direct, workflow, and DAG execution paths before merging duplicate implementations.

### Phase 4 — Naming, duplication, and dead code
- Inventory imports and call sites before renaming or deleting modules.
- Standardize new Python names on snake_case, classes on PascalCase, constants on UPPER_SNAKE_CASE.
- Remove only code proven unreachable or superseded; preserve compatibility wrappers and public API names.
- Add deprecation warnings before removing externally used entry points.

### Phase 5 — State and persistence
- Define explicit per-task/session state; avoid process-global mutable state for concurrent tasks.
- Keep durable goal/checkpoint state in the persistence layer.
- Separate transient observations from durable execution state and include observation freshness/version identifiers.
- Add concurrency and restart/recovery tests.

### Phase 6 — Error handling and observability
- Define typed domain errors and stable API error responses.
- Translate known adapter failures at module boundaries; do not hide broad exceptions or return success-shaped fallbacks.
- Include request/task correlation IDs, structured logs, bounded timeouts, and redaction of secrets and screen contents.
- Test failure paths as carefully as success paths.

### Phase 7 — Verification and cleanup
- Run the full supported test matrix on Windows for UI-dependent code and on supported Python versions for portable logic.
- Add import/entry-point smoke tests and end-to-end desktop scenarios.
- Compare API contracts and performance before/after each migration.
- Delete dead code only after static reference checks, tests, and compatibility review.

## Acceptance criteria

- Existing public imports and documented API routes continue to work during migration.
- Configuration is environment-driven, validated, and documented; real secrets stay out of Git.
- Route modules do not contain desktop business logic.
- One action contract is shared by supported execution paths.
- Errors are explicit, typed, and traceable; unexpected errors are not silently swallowed.
- Session state is isolated between concurrent tasks.
- Each structural move includes tests and a rollback path.
- The full test suite and Windows integration checks pass before merge.

## Working rule

Do not combine a broad file move, behavior changes, and dead-code deletion in one unreviewable commit. Ship small, testable phases and merge only after the relevant CI and Windows smoke tests pass.
