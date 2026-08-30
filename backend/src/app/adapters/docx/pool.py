"""Bounded async pool of warm stateless DOCX workers."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.adapters.docx.contracts import (
    DocxProcessorErrorCode,
    DocxProcessorOperation,
    ProcessorResponse,
)
from app.adapters.docx.worker import DocxWorker
from app.errors import ErrorCode, app_error

MAX_REQUESTS_PER_WORKER = 100
MAX_WORKING_SET_BYTES = 512 * 1024 * 1024


class DocxProcessorPool:
    def __init__(self, executable: Path, worker_count: int) -> None:
        self._executable = executable
        self._worker_count = worker_count
        self._idle: asyncio.Queue[DocxWorker] = asyncio.Queue(worker_count)
        self._admission = asyncio.Semaphore(worker_count * 5)
        self._workers: set[DocxWorker] = set()
        self._closing = False

    async def start(self) -> None:
        try:
            for _ in range(self._worker_count):
                worker = await self._new_worker()
                self._idle.put_nowait(worker)
        except BaseException:
            await self.close()
            raise

    async def execute(
        self,
        operation: DocxProcessorOperation,
        payload: object,
        *,
        timeout: float,
    ) -> ProcessorResponse:
        if self._closing:
            raise app_error(ErrorCode.DOCX_PROCESSING_FAILED)
        try:
            await asyncio.wait_for(self._admission.acquire(), timeout=0.01)
        except TimeoutError as exc:
            raise app_error(ErrorCode.DOCX_PROCESSOR_BUSY) from exc

        worker = await self._idle.get()
        returned = False
        try:
            response = await asyncio.wait_for(worker.execute(operation, payload), timeout=timeout)
            if not response.ok:
                self._idle.put_nowait(worker)
                returned = True
                self._raise_processor_error(response)
            if (
                worker.request_count >= MAX_REQUESTS_PER_WORKER
                or response.working_set_bytes >= MAX_WORKING_SET_BYTES
            ):
                await self._replace(worker)
            else:
                self._idle.put_nowait(worker)
            returned = True
            return response
        except asyncio.CancelledError:
            await self._replace(worker)
            returned = True
            raise
        except BaseException:
            if not returned:
                await self._replace(worker)
                returned = True
            raise
        finally:
            self._admission.release()

    async def close(self) -> None:
        self._closing = True
        workers = tuple(self._workers)
        self._workers.clear()
        await asyncio.gather(*(worker.close() for worker in workers), return_exceptions=True)

    async def _new_worker(self) -> DocxWorker:
        worker = DocxWorker(self._executable)
        await worker.start()
        self._workers.add(worker)
        return worker

    async def _replace(self, worker: DocxWorker) -> None:
        self._workers.discard(worker)
        await worker.close()
        if not self._closing:
            replacement = await self._new_worker()
            self._idle.put_nowait(replacement)

    @staticmethod
    def _raise_processor_error(response: ProcessorResponse) -> None:
        error = response.error
        if error is None:
            raise app_error(ErrorCode.DOCX_PROCESSING_FAILED)
        if error.code is DocxProcessorErrorCode.UNSUPPORTED_DOCX_FEATURE:
            raise app_error(
                ErrorCode.DOCX_UNSUPPORTED_FEATURE,
                details={"feature": error.feature or "unknown"},
            )
        if error.code in {
            DocxProcessorErrorCode.INVALID_TARGET,
            DocxProcessorErrorCode.OVERLAPPING_TARGETS,
            DocxProcessorErrorCode.INVALID_REPLACEMENT,
        }:
            raise app_error(ErrorCode.INVALID_DOCX_TEXT_TARGET)
        raise app_error(ErrorCode.DOCX_PROCESSING_FAILED, details={"processor_code": error.code})
