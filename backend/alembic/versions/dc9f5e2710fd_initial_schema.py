"""initial schema

Revision ID: dc9f5e2710fd
Revises:
Create Date: 2026-10-22 20:34:00.441532

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "dc9f5e2710fd"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint("name", name=op.f("uq_datasets_name")),
    )
    op.create_table(
        "judge_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("evaluator", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("judge_model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judge_cache")),
        sa.UniqueConstraint("cache_key", name=op.f("uq_judge_cache_cache_key")),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("validation_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_count >= 0", name=op.f("ck_dataset_versions_item_count_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_dataset_versions_dataset_id_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
        sa.UniqueConstraint("dataset_id", "content_hash", name="uq_dataset_versions_dataset_hash"),
        sa.UniqueConstraint(
            "dataset_id", "version_number", name="uq_dataset_versions_dataset_version"
        ),
    )
    with op.batch_alter_table("dataset_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_dataset_versions_dataset_id"), ["dataset_id"], unique=False
        )

    op.create_table(
        "dataset_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("ground_truth", sa.Text(), nullable=False),
        sa.Column("reference_contexts", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_dataset_items_ordinal_nonnegative")),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_dataset_items_dataset_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_items")),
        sa.UniqueConstraint(
            "dataset_version_id", "ordinal", name="uq_dataset_items_version_ordinal"
        ),
    )
    with op.batch_alter_table("dataset_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_dataset_items_dataset_version_id"), ["dataset_version_id"], unique=False
        )

    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "partial",
                "failed",
                "cancelled",
                name="runstatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "dashboard",
                "cli",
                "ci",
                "demo",
                name="runsource",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "target_kind",
            sa.Enum(
                "reference",
                "http",
                name="targetkind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("target_config", sa.JSON(), nullable=False),
        sa.Column("pipeline_config", sa.JSON(), nullable=False),
        sa.Column(
            "judge_mode",
            sa.Enum(
                "llm",
                "mock",
                name="judgemode",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("judge_model", sa.String(length=200), nullable=False),
        sa.Column("judge_repeats", sa.Integer(), nullable=False),
        sa.Column("warmup_count", sa.Integer(), nullable=False),
        sa.Column("evaluator_config", sa.JSON(), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("baseline_run_id", sa.Uuid(), nullable=True),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("git_branch", sa.String(length=255), nullable=True),
        sa.Column("pull_request_number", sa.Integer(), nullable=True),
        sa.Column("total_queries", sa.Integer(), nullable=False),
        sa.Column("completed_queries", sa.Integer(), nullable=False),
        sa.Column("failed_queries", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "completed_queries + failed_queries <= total_queries",
            name=op.f("ck_runs_progress_within_total"),
        ),
        sa.CheckConstraint(
            "completed_queries >= 0", name=op.f("ck_runs_completed_queries_nonnegative")
        ),
        sa.CheckConstraint("failed_queries >= 0", name=op.f("ck_runs_failed_queries_nonnegative")),
        sa.CheckConstraint("judge_repeats >= 1", name=op.f("ck_runs_judge_repeats_positive")),
        sa.CheckConstraint("total_queries >= 0", name=op.f("ck_runs_total_queries_nonnegative")),
        sa.CheckConstraint("warmup_count >= 0", name=op.f("ck_runs_warmup_count_nonnegative")),
        sa.ForeignKeyConstraint(
            ["baseline_run_id"],
            ["runs.id"],
            name=op.f("fk_runs_baseline_run_id_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_runs_dataset_version_id_dataset_versions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
    )
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_runs_config_hash"), ["config_hash"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_runs_dataset_version_id"), ["dataset_version_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_runs_provider_name"), ["provider_name"], unique=False)
        batch_op.create_index("ix_runs_status_created_at", ["status", "created_at"], unique=False)

    op.create_table(
        "query_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "succeeded",
                "failed",
                name="queryresultstatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("contexts", sa.JSON(), nullable=False),
        sa.Column("ttft_ms", sa.Float(), nullable=True),
        sa.Column(
            "ttft_source",
            sa.Enum(
                "measured",
                "target_reported",
                "demo",
                name="ttftsource",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("tokens_per_second", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(ttft_ms IS NULL) = (ttft_source IS NULL)",
            name=op.f("ck_query_results_ttft_provenance_consistency"),
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name=op.f("ck_query_results_input_tokens_nonnegative"),
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name=op.f("ck_query_results_latency_nonnegative"),
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name=op.f("ck_query_results_output_tokens_nonnegative"),
        ),
        sa.CheckConstraint(
            "tokens_per_second IS NULL OR tokens_per_second >= 0",
            name=op.f("ck_query_results_tokens_per_second_nonnegative"),
        ),
        sa.CheckConstraint(
            "ttft_ms IS NULL OR latency_ms IS NULL OR ttft_ms <= latency_ms",
            name=op.f("ck_query_results_ttft_not_after_total"),
        ),
        sa.CheckConstraint(
            "ttft_ms IS NULL OR ttft_ms >= 0", name=op.f("ck_query_results_ttft_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_item_id"],
            ["dataset_items.id"],
            name=op.f("fk_query_results_dataset_item_id_dataset_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_query_results_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_query_results")),
        sa.UniqueConstraint("run_id", "dataset_item_id", name="uq_query_results_run_item"),
    )
    with op.batch_alter_table("query_results", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_query_results_dataset_item_id"), ["dataset_item_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_query_results_run_id"), ["run_id"], unique=False)

    op.create_table(
        "metric_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_result_id", sa.Uuid(), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("sample_index", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "succeeded",
                "failed",
                name="judgmentstatus",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evaluator", sa.String(length=64), nullable=False),
        sa.Column("judge_model", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("judge_cached", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sample_index >= 0", name=op.f("ck_metric_scores_sample_index_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["query_result_id"],
            ["query_results.id"],
            name=op.f("fk_metric_scores_query_result_id_query_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_scores")),
        sa.UniqueConstraint(
            "query_result_id",
            "metric_name",
            "sample_index",
            name="uq_metric_scores_result_metric_sample",
        ),
    )
    with op.batch_alter_table("metric_scores", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_metric_scores_query_result_id"), ["query_result_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("metric_scores", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_metric_scores_query_result_id"))

    op.drop_table("metric_scores")
    with op.batch_alter_table("query_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_query_results_run_id"))
        batch_op.drop_index(batch_op.f("ix_query_results_dataset_item_id"))

    op.drop_table("query_results")
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_index("ix_runs_status_created_at")
        batch_op.drop_index(batch_op.f("ix_runs_provider_name"))
        batch_op.drop_index(batch_op.f("ix_runs_dataset_version_id"))
        batch_op.drop_index(batch_op.f("ix_runs_config_hash"))

    op.drop_table("runs")
    with op.batch_alter_table("dataset_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_dataset_items_dataset_version_id"))

    op.drop_table("dataset_items")
    with op.batch_alter_table("dataset_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_dataset_versions_dataset_id"))

    op.drop_table("dataset_versions")
    op.drop_table("judge_cache")
    op.drop_table("datasets")
