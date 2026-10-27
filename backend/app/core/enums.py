from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunSource(StrEnum):
    DASHBOARD = "dashboard"
    CLI = "cli"
    CI = "ci"
    DEMO = "demo"


class TargetKind(StrEnum):
    REFERENCE = "reference"
    HTTP = "http"


class JudgeMode(StrEnum):
    LLM = "llm"
    MOCK = "mock"


class QueryResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JudgmentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MetricName(StrEnum):
    CONTEXT_RECALL = "context_recall"
    FAITHFULNESS = "faithfulness"
    ANSWER_RELEVANCE = "answer_relevance"
    HALLUCINATION_RATE = "hallucination_rate"


class TTFTSource(StrEnum):
    MEASURED = "measured"
    TARGET_REPORTED = "target_reported"
    DEMO = "demo"
