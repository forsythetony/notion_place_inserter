"""Usage accounting service for recording LLM tokens and external API calls."""

from __future__ import annotations

import uuid

from loguru import logger

from app.domain.runs import UsageRecord


class UsageAccountingService:
    """Records usage (LLM tokens, external API calls) via RunRepository."""

    def __init__(self, run_repository: object) -> None:
        self._run_repo = run_repository

    def record_llm_tokens(
        self,
        job_run_id: str,
        owner_user_id: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        step_run_id: str | None = None,
        model: str | None = None,
    ) -> None:
        """Record LLM token usage."""
        total = prompt_tokens + completion_tokens
        record = UsageRecord(
            id=f"usage_{uuid.uuid4().hex[:12]}",
            job_run_id=job_run_id,
            usage_type="llm_tokens",
            provider=provider,
            metric_name="total_tokens",
            metric_value=total,
            owner_user_id=owner_user_id,
            step_run_id=step_run_id,
            metadata={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "model": model or "claude-sonnet-4-20250514",
            },
        )
        try:
            self._run_repo.save_usage_record(record)
        except Exception as e:
            logger.exception(
                "usage_accounting_save_llm_tokens_failed | job_run_id={} provider={} error={}",
                job_run_id,
                provider,
                e,
            )

    def record_external_api_call(
        self,
        job_run_id: str,
        owner_user_id: str,
        provider: str,
        operation: str,
        *,
        step_run_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record an external API call (count=1)."""
        record = UsageRecord(
            id=f"usage_{uuid.uuid4().hex[:12]}",
            job_run_id=job_run_id,
            usage_type="external_api_call",
            provider=provider,
            metric_name=operation,
            metric_value=1,
            owner_user_id=owner_user_id,
            step_run_id=step_run_id,
            metadata=metadata,
        )
        try:
            self._run_repo.save_usage_record(record)
        except Exception as e:
            logger.exception(
                "usage_accounting_save_external_api_failed | job_run_id={} provider={} operation={} error={}",
                job_run_id,
                provider,
                operation,
                e,
            )
