"""Workflow engine public API for P2 incremental runtime.

Exports the minimal surface needed by higher-level callers:
``WorkflowEngine`` to run definitions, ``WorkflowDefinition``/``Step`` to
build them, ``RunContext`` for variable scope, and ``WorkflowResult`` /
``WorkflowEvent`` / ``WorkflowErrorCode`` for structured outputs and events.
"""

from __future__ import annotations

from ai.core.workflow.errors import WorkflowErrorCode, workflow_error_code_from_name
from ai.core.workflow.events import WorkflowEvent, WorkflowEventFactory
from ai.core.workflow.context import RunContext, Scope
from ai.core.workflow.definition import Step, StepKind, WorkflowDefinition
from ai.core.workflow.engine import WorkflowEngine, WorkflowResult

__all__ = [
  "WorkflowEngine",
  "WorkflowResult",
  "WorkflowEvent",
  "WorkflowEventFactory",
  "WorkflowErrorCode",
  "workflow_error_code_from_name",
  "WorkflowDefinition",
  "Step",
  "StepKind",
  "RunContext",
  "Scope",
]
