"""Sandbox pooling for fast environment acquisition.

This module provides a pool of pre-warmed sandbox environments
to eliminate the overhead of creating virtual environments on each use.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import venv
from dataclasses import dataclass
from queue import Queue, Empty
from typing import Optional, Set

from ..sandbox.executor import SandboxExecutor


@dataclass
class PooledSandbox:
    """A sandbox from the pool with automatic return on cleanup."""
    executor: SandboxExecutor
    pool: "SandboxPool"
    _returned: bool = False

    def __enter__(self):
        return self.executor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

    def release(self):
        """Return this sandbox to the pool."""
        if not self._returned:
            self.pool.release(self)
            self._returned = True


class SandboxPool:
    """Pool of pre-warmed sandbox environments.

    This eliminates the overhead of creating virtual environments
    by maintaining a pool of ready-to-use sandboxes.

    Usage:
        pool = SandboxPool(pool_size=3, workspace_base="./workspaces")
        pool.start()

        # Acquire a sandbox (fast, ~100ms vs ~30s for creation)
        with pool.acquire() as sandbox:
            sandbox.run_python_file("test.py")

        # Pool stops automatically when out of scope
    """

    def __init__(
        self,
        pool_size: int = 3,
        workspace_base: str = "./workspaces",
        timeout: int = 60,
    ):
        self.pool_size = pool_size
        self.workspace_base = workspace_base
        self.timeout = timeout
        self._pool: Queue[PooledSandbox] = Queue(maxsize=pool_size)
        self._semaphore = threading.Semaphore(pool_size)
        self._lock = threading.Lock()
        self._active: Set[int] = set()
        self._pool_id = id(self)
        self._started = False

    def start(self) -> None:
        """Start the pool and pre-warm sandboxes."""
        if self._started:
            return

        # Ensure workspace base exists
        os.makedirs(self.workspace_base, exist_ok=True)

        # Pre-warm pool
        for i in range(self.pool_size):
            sandbox = self._create_sandbox(i)
            pooled = PooledSandbox(executor=sandbox, pool=self)
            self._pool.put(pooled)

        self._started = True

    def _create_sandbox(self, index: int) -> SandboxExecutor:
        """Create a new sandbox environment."""
        workspace_path = os.path.join(
            self.workspace_base,
            f"pool_{self._pool_id}_{index}"
        )

        # Clean up if exists
        if os.path.exists(workspace_path):
            shutil.rmtree(workspace_path)

        os.makedirs(workspace_path, exist_ok=True)

        # Create sandbox executor
        sandbox = SandboxExecutor(
            workspace_path=workspace_path,
            timeout=self.timeout,
        )

        # Pre-create virtual environment
        sandbox._create_venv()

        return sandbox

    def acquire(self, timeout: Optional[float] = None) -> PooledSandbox:
        """Acquire a sandbox from the pool.

        Args:
            timeout: Maximum time to wait for a sandbox (seconds)

        Returns:
            PooledSandbox that auto-returns to pool on release

        Raises:
            TimeoutError: If no sandbox available within timeout
        """
        if not self._started:
            self.start()

        if timeout is None:
            timeout = 5.0

        if not self._semaphore.acquire(timeout=timeout):
            raise TimeoutError(f"No sandbox available after {timeout}s")

        try:
            pooled = self._pool.get(block=False)
            with self._lock:
                self._active.add(id(pooled.executor))
            pooled._returned = False
            return pooled
        except Empty:
            self._semaphore.release()
            raise TimeoutError("Pool is empty despite semaphore")

    def release(self, pooled: PooledSandbox) -> None:
        """Return a sandbox to the pool."""
        # Reset the sandbox (lightweight cleanup)
        self._reset_sandbox(pooled.executor)

        with self._lock:
            self._active.discard(id(pooled.executor))

        pooled._returned = True
        self._pool.put(pooled)
        self._semaphore.release()

    def _reset_sandbox(self, sandbox: SandboxExecutor) -> None:
        """Reset a sandbox for reuse (lightweight cleanup)."""
        workspace = sandbox.workspace_path

        # Remove all files except venv
        for item in os.listdir(workspace):
            if item == ".nano_ant_venv":
                continue

            item_path = os.path.join(workspace, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
            except Exception:
                pass  # Ignore cleanup errors

        # Reset installed packages tracking
        sandbox._installed_packages.clear()

    def get_stats(self) -> dict:
        """Get pool statistics."""
        return {
            "pool_size": self.pool_size,
            "available": self._pool.qsize(),
            "active": len(self._active),
            "started": self._started,
        }

    def cleanup(self) -> None:
        """Clean up all sandboxes in the pool."""
        if not self._started:
            return

        # Drain pool
        while not self._pool.empty():
            try:
                pooled = self._pool.get(block=False)
                self._cleanup_sandbox(pooled.executor)
            except Empty:
                break

        # Clean up workspace base
        if os.path.exists(self.workspace_base):
            for item in os.listdir(self.workspace_base):
                if f"pool_{self._pool_id}_" in item:
                    try:
                        shutil.rmtree(os.path.join(self.workspace_base, item))
                    except Exception:
                        pass

        self._started = False

    def _cleanup_sandbox(self, sandbox: SandboxExecutor) -> None:
        """Fully clean up a sandbox."""
        try:
            sandbox.cleanup()
            if os.path.exists(sandbox.workspace_path):
                shutil.rmtree(sandbox.workspace_path)
        except Exception:
            pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False


class NullSandboxPool:
    """Null object pattern for when pooling is disabled."""

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def acquire(self, timeout=None):
        raise NotImplementedError("Sandbox pooling is disabled")

    def release(self, pooled):
        pass

    def get_stats(self):
        return {"disabled": True}

    def cleanup(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
