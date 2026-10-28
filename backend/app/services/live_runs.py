from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.storage.models import Run

LimitReason = Literal["per_ip", "daily"]


@dataclass(frozen=True, slots=True)
class LiveRunLimit:
    reason: LimitReason
    message: str
    retry_after_seconds: int
    limit: int


class LiveRunLimitError(RuntimeError):
    def __init__(self, limit: LiveRunLimit) -> None:
        super().__init__(limit.message)
        self.limit = limit


# The free deployment runs one API process. This lock makes the check-then-create sequence atomic
# without adding a distributed lock or a second database round trip.
_limit_lock = asyncio.Lock()


def client_ip_from_request(request: Request) -> str:
    """Resolve the caller IP behind Render's proxy, falling back to the socket peer."""

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",", maxsplit=1)[0].strip()
        if candidate:
            return candidate
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def hash_client_ip(settings: Settings, client_ip: str) -> str:
    salted = f"{settings.live_run_ip_hash_salt_value}:{client_ip}".encode()
    return hashlib.sha256(salted).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


async def _daily_limit(
    session: AsyncSession,
    settings: Settings,
    now: datetime,
) -> LiveRunLimit | None:
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    used = int(
        await session.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.client_ip_hash.is_not(None), Run.created_at >= start_of_day)
        )
        or 0
    )
    if used < settings.live_run_daily_cap:
        return None
    return LiveRunLimit(
        reason="daily",
        message=(
            "The free-tier daily live-run budget is exhausted. Live runs are paused until "
            "00:00 UTC; the recorded demo remains available."
        ),
        retry_after_seconds=_seconds_until_utc_midnight(now),
        limit=settings.live_run_daily_cap,
    )


async def _per_ip_limit(
    session: AsyncSession,
    settings: Settings,
    *,
    ip_hash: str,
    now: datetime,
) -> LiveRunLimit | None:
    window_start = now - timedelta(seconds=settings.live_run_rate_window_seconds)
    filters = (Run.client_ip_hash == ip_hash, Run.created_at >= window_start)
    used = int(await session.scalar(select(func.count()).select_from(Run).where(*filters)) or 0)
    if used < settings.live_run_per_ip_limit:
        return None

    oldest = await session.scalar(select(func.min(Run.created_at)).where(*filters))
    retry_after = settings.live_run_rate_window_seconds
    if oldest is not None:
        elapsed = max(0.0, (now - _as_utc(oldest)).total_seconds())
        retry_after = max(1, int(settings.live_run_rate_window_seconds - elapsed) + 1)
    return LiveRunLimit(
        reason="per_ip",
        message=(
            "This network has reached the live-run rate limit. Try again later, or use the "
            "recorded demo in the meantime."
        ),
        retry_after_seconds=retry_after,
        limit=settings.live_run_per_ip_limit,
    )


@asynccontextmanager
async def reserve_live_run_slot(
    session: AsyncSession,
    settings: Settings,
    client_ip: str,
) -> AsyncIterator[str | None]:
    """Check the active live-run budget and hold a slot until the run is committed.

    When protection is disabled this is a no-op that yields ``None``. The caller is responsible for
    passing the returned hash to ``create_run`` so the row participates in future counts.
    """

    if not settings.live_run_protection:
        yield None
        return

    ip_hash = hash_client_ip(settings, client_ip)
    async with _limit_lock:
        now = datetime.now(UTC)
        daily = await _daily_limit(session, settings, now)
        if daily is not None:
            raise LiveRunLimitError(daily)
        per_ip = await _per_ip_limit(session, settings, ip_hash=ip_hash, now=now)
        if per_ip is not None:
            raise LiveRunLimitError(per_ip)
        yield ip_hash
