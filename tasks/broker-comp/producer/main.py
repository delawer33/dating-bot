import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

import redis_producer
import rmq_producer
from models import BrokerType, RunConfig

_current_task: asyncio.Task | None = None
_stop_event: asyncio.Event = asyncio.Event()
_sent_counter: list[int] = [0]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if _current_task and not _current_task.done():
        _stop_event.set()
        _current_task.cancel()


app = FastAPI(title="Benchmark Producer", lifespan=lifespan)


@app.post("/start", status_code=202)
async def start(config: RunConfig) -> dict:
    global _current_task, _stop_event, _sent_counter

    if _current_task and not _current_task.done():
        raise HTTPException(status_code=409, detail="A run is already in progress")

    _stop_event = asyncio.Event()
    _sent_counter = [0]

    if config.broker == BrokerType.rmq:
        coro = rmq_producer.run(config, _stop_event, _sent_counter)
    else:
        coro = redis_producer.run(config, _stop_event, _sent_counter)

    def _log_task_failure(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            print(f"[producer] benchmark task failed: {exc!r}", flush=True)

    _current_task = asyncio.create_task(coro)
    _current_task.add_done_callback(_log_task_failure)
    return {"status": "started", "broker": config.broker, "config": config.config}


@app.post("/stop")
async def stop() -> dict:
    global _current_task

    if not _current_task or _current_task.done():
        return {"status": "idle", "sent_count": _sent_counter[0]}

    _stop_event.set()
    try:
        await asyncio.wait_for(_current_task, timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        _current_task.cancel()

    return {"status": "stopped", "sent_count": _sent_counter[0]}


@app.get("/status")
async def status() -> dict:
    running = _current_task is not None and not _current_task.done()
    return {"running": running, "sent_count": _sent_counter[0]}


@app.post("/flush")
async def flush(broker: str = Query(..., min_length=1, description="rmq or redis_streams")):
    """
    Clear broker state between benchmark runs.

    Returns JSON for all outcomes so the runner can print `detail` on failure.
    (Plain Starlette 500 pages hide the underlying error.)
    """
    global _current_task

    if _current_task is not None and not _current_task.done():
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Producer run still active; POST /stop before flush",
            },
        )

    try:
        bt = BrokerType(broker.strip())
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"detail": f"unknown broker {broker!r}; use rmq or redis_streams"},
        )

    try:
        if bt == BrokerType.rmq:
            await rmq_producer.flush_queue()
        else:
            await redis_producer.flush_stream()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "detail": f"flush failed ({bt.value}): {type(exc).__name__}: {exc}",
            },
        )

    return {"status": "flushed", "broker": bt.value}
