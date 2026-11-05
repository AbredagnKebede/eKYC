"""Background cleanup daemon for expired incomplete applications (CH-03)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from src.models.base import async_session_factory
from src.services.onboarding import OnboardingService

logger = logging.getLogger("ekyc.worker.cleanup")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

INTERVAL_SECONDS = float(os.getenv("CLEANUP_INTERVAL_SECONDS", "60"))
_shutdown = asyncio.Event()


def _handle_signal(*_: object) -> None:
    _shutdown.set()


async def run_cleanup_loop() -> None:
    onboarding = OnboardingService()
    logger.info("Cleanup worker started (interval=%ss)", INTERVAL_SECONDS)
    while not _shutdown.is_set():
        try:
            async with async_session_factory() as session:
                expired = await onboarding.expire_inactive_applications(session)
                if expired:
                    logger.info("Expired %s inactive application(s)", expired)
        except Exception:
            logger.exception("Cleanup cycle failed")
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
    logger.info("Cleanup worker stopped")


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handle_signal())
    loop.run_until_complete(run_cleanup_loop())


if __name__ == "__main__":
    main()
