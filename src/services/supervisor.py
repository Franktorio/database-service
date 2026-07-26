# ~/src/services/supervisor.py
# Async task supervisor that monitors and restarts background tasks if they fail.

import asyncio
from collections.abc import Awaitable, Callable

from config.loader import DEFAULT_TASK_RESTART_DELAY, DEFAULT_TASK_RESTART_ATTEMPTS

from src.services.system.logging import log_message

PRINT_PREFIX = "TASK SUPERVISOR"

class TaskSupervisor:

    def __init__(self,
                coroutine_func: Callable[[], Awaitable],
                name: str | None = "UNKNOWN_TASK",
                restart_delay: int | None = DEFAULT_TASK_RESTART_DELAY,
                restart_attempts: int | None = DEFAULT_TASK_RESTART_ATTEMPTS):
        self.coroutine_func = coroutine_func
        self.name = name
        self.restart_delay = restart_delay
        self.restart_attempts = restart_attempts

        self._task: asyncio.Task | None = None
        self._supervisor_task: asyncio.Task | None = None
        self._shutdown = False

    async def _run_supervisor(self):
        """Internal supervisor loop."""

        attempts = 0
        current_delay = self.restart_delay

        while not self._shutdown:
            try:
                log_message(f"[INFO] [{PRINT_PREFIX}] Starting task {self.name}.")

                self._task = asyncio.create_task(
                    self.coroutine_func(),
                    name=self.name
                )

                await self._task

                if self._shutdown:
                    break

                attempts += 1

                log_message(f"[WARNING] [{PRINT_PREFIX}] Task {self.name} exited unexpectedly.")

            except asyncio.CancelledError:
                log_message(f"[INFO] [{PRINT_PREFIX}] Supervisor for task {self.name} was cancelled.")
                break

            except (RuntimeError, ValueError, TypeError, OSError) as e:
                attempts += 1

                log_message(
                    f"[ERROR] [{PRINT_PREFIX}] Task {self.name} failed with exception: {e}. "
                    f"Attempt {attempts}/{self.restart_attempts}."
                )

            if self.restart_attempts is not None and attempts >= self.restart_attempts:
                log_message(
                    f"[ERROR] [{PRINT_PREFIX}] Task {self.name} reached maximum restart attempts. "
                    f"Not restarting."
                )
                break

            log_message(
                f"[INFO] [{PRINT_PREFIX}] Restarting task {self.name} in {current_delay} seconds."
            )

            try:
                await asyncio.sleep(current_delay)
            except asyncio.CancelledError:
                break

            current_delay *= 2

        log_message(f"[INFO] [{PRINT_PREFIX}] Supervisor for task {self.name} has stopped.")

    def supervise_task(self):
        """Start supervising the task."""

        if self._supervisor_task is not None:
            return self._supervisor_task

        self._shutdown = False

        self._supervisor_task = asyncio.create_task(
            self._run_supervisor(),
            name=f"{self.name}_SUPERVISOR"
        )

        return self._supervisor_task

    async def cancel(self):
        """Cancel the supervised task."""

        log_message(f"[INFO] [{PRINT_PREFIX}] Cancelling task {self.name}.")

        self._shutdown = True

        if self._task is not None and not self._task.done():
            self._task.cancel()

        if self._supervisor_task is not None and not self._supervisor_task.done():
            self._supervisor_task.cancel()

        await asyncio.gather(
            *(task for task in [self._task, self._supervisor_task] if task is not None),
            return_exceptions=True
        )

        log_message(f"[INFO] [{PRINT_PREFIX}] Task {self.name} cancelled.")