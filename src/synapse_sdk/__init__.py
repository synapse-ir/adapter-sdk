"""synapse-adapter-sdk public API."""

from synapse_sdk.base import AdapterBase, AdapterConfigurationError
from synapse_sdk.cache import (
    AdapterInstanceCache,
    AdapterLoadError,
    CalibrationBuffer,
    CalibrationSignal,
    ContextStore,
    HeartbeatCache,
    HeartbeatResponse,
    InMemoryContextStore,
    RedisContextStore,
    RouteCandidate,
    RouteCacheClient,
    RouteRequest,
    RouteResponse,
    S3ContextStore,
    make_context_store,
)
from synapse_sdk.tracing import adapter_span, make_child_traceparent, propagate_trace_context
from synapse_sdk.types import (
    BranchRole,
    CanonicalIR,
    ComplianceEnvelope,
    Domain,
    Entity,
    FailedStage,
    FailurePolicy,
    PartialCompletionResponse,
    Payload,
    ProvenanceEntry,
    TaskHeader,
    TaskType,
    TraceContext,
)
from synapse_sdk.validator import (
    AdapterValidationError,
    AdapterValidationResult,
    AdapterValidator,
    Severity,
    ValidationFailure,
)

__all__ = [
    # base
    "AdapterBase",
    "AdapterConfigurationError",
    # types
    "BranchRole",
    "CanonicalIR",
    "ComplianceEnvelope",
    "Domain",
    "Entity",
    "FailedStage",
    "FailurePolicy",
    "PartialCompletionResponse",
    "Payload",
    "ProvenanceEntry",
    "TaskHeader",
    "TaskType",
    "TraceContext",
    # tracing — G-S01
    "adapter_span",
    "make_child_traceparent",
    "propagate_trace_context",
    # validator
    "AdapterValidationError",
    "AdapterValidationResult",
    "AdapterValidator",
    "Severity",
    "ValidationFailure",
    # cache — C1
    "AdapterInstanceCache",
    "AdapterLoadError",
    # cache — C2
    "RouteCacheClient",
    "RouteRequest",
    "RouteResponse",
    "RouteCandidate",
    # cache — C3
    "HeartbeatCache",
    "HeartbeatResponse",
    # cache — C4
    "ContextStore",
    "InMemoryContextStore",
    "RedisContextStore",
    "S3ContextStore",
    "make_context_store",
    # cache — C5
    "CalibrationBuffer",
    "CalibrationSignal",
]
