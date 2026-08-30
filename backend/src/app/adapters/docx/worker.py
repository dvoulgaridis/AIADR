"""One stateless stdio DOCX processor worker."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
from pathlib import Path

from app.adapters.docx.contracts import (
    DocxProcessorOperation,
    HandshakeResult,
    ProcessorResponse,
)
from app.adapters.docx.framing import read_frame, write_frame
from app.core.ids import new_correlation_id
from app.errors import ErrorCode, app_error

logger = logging.getLogger(__name__)


class DocxWorker:
    """Own one processor child and exactly one in-flight request."""

    def __init__(self, executable: Path) -> None:
        self._executable = executable
        self._process: subprocess.Popen[bytes] | None = None
        self._exchange_task: asyncio.Task[ProcessorResponse] | None = None
        self._stderr_thread: threading.Thread | None = None
        self.request_count = 0

    async def start(self) -> None:
        environment = {
            name: value
            for name, value in os.environ.items()
            if name in {"DOTNET_ROOT", "HOME", "PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR"}
        }
        environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
        try:
            process = await asyncio.to_thread(
                subprocess.Popen,
                [str(self._executable), "host", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
            )
            self._process = process
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(process,),
                name="aiadr-docx-stderr",
                daemon=True,
            )
            self._stderr_thread.start()
            result = await self.execute(DocxProcessorOperation.HANDSHAKE, {})
            handshake = HandshakeResult.model_validate(result.payload)
        except (EOFError, OSError) as exc:
            await self.close()
            raise app_error(ErrorCode.DOCX_PROCESSOR_MISSING) from exc
        except BaseException:
            await self.close()
            raise
        if set(handshake.operations) != {
            DocxProcessorOperation.INSPECT,
            DocxProcessorOperation.RENDER,
        }:
            await self.close()
            raise app_error(ErrorCode.DOCX_PROCESSING_FAILED)
        self.request_count = 0

    async def execute(
        self,
        operation: DocxProcessorOperation,
        payload: object,
    ) -> ProcessorResponse:
        process = self._process
        if process is None or process.poll() is not None or self._exchange_task is not None:
            raise app_error(ErrorCode.DOCX_PROCESSING_FAILED)
        request_id = new_correlation_id()
        exchange_task = asyncio.create_task(
            asyncio.to_thread(
                self._exchange,
                process,
                {
                    "request_id": request_id,
                    "operation": operation,
                    "payload": payload,
                },
            )
        )
        self._exchange_task = exchange_task
        try:
            response = await asyncio.shield(exchange_task)
        except asyncio.CancelledError:
            raise
        except BaseException:
            self._exchange_task = None
            raise
        else:
            self._exchange_task = None
        if response.request_id != request_id:
            raise app_error(ErrorCode.DOCX_PROCESSING_FAILED)
        self.request_count += 1
        return response

    async def close(self) -> None:
        process = self._process
        self._process = None
        exchange_task = self._exchange_task
        self._exchange_task = None
        stderr_thread = self._stderr_thread
        self._stderr_thread = None
        if process is None:
            if exchange_task is not None:
                await asyncio.gather(exchange_task, return_exceptions=True)
            return

        try:
            if process.poll() is None:
                process.terminate()
            await asyncio.to_thread(self._wait_for_exit, process)
        finally:
            if exchange_task is not None:
                await asyncio.gather(exchange_task, return_exceptions=True)
            if stderr_thread is not None:
                await asyncio.to_thread(stderr_thread.join)
            await asyncio.to_thread(self._close_pipes, process)

    @staticmethod
    def _exchange(process: subprocess.Popen[bytes], request: object) -> ProcessorResponse:
        if process.stdin is None or process.stdout is None:
            raise OSError("DOCX processor pipes are unavailable.")
        write_frame(process.stdin, request)
        return ProcessorResponse.model_validate(read_frame(process.stdout))

    @staticmethod
    def _wait_for_exit(process: subprocess.Popen[bytes]) -> None:
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    @staticmethod
    def _close_pipes(process: subprocess.Popen[bytes]) -> None:
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()

    @staticmethod
    def _drain_stderr(process: subprocess.Popen[bytes]) -> None:
        if process.stderr is None:
            return
        try:
            while process.stderr.readline():
                logger.warning("DOCX processor emitted stderr output")
        except OSError:
            return
