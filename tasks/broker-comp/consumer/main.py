import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

import redis_consumer
import rmq_consumer
from metrics_store import MetricsStore
from models import BrokerType, RunConfig

_current_task: asyncio.Task | None = None
_stop_event: asyncio.Event = asyncio.Event()
_store: MetricsStore = MetricsStore()
_run_config: RunConfig | None = None
_sent_count: int = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if _current_task and not _current_task.done():
        _stop_event.set()
        _current_task.cancel()


app = FastAPI(title="Benchmark Consumer", lifespan=lifespan)


@app.post("/start", status_code=202)
async def start(config: RunConfig) -> dict:
    global _current_task, _stop_event, _store, _run_config

    if _current_task and not _current_task.done():
        raise HTTPException(status_code=409, detail="A run is already in progress")

    _stop_event = asyncio.Event()
    _store = MetricsStore(warmup_seconds=float(config.warmup_seconds))
    _run_config = config

    if config.broker == BrokerType.rmq:
        await rmq_consumer.prepare_queue(config.config)
        coro = rmq_consumer.run(config.config, _store, _stop_event)
    else:
        await redis_consumer.prepare(config.config)
        coro = redis_consumer.run(config.config, _store, _stop_event)

    def _log_task_failure(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            print(f"[consumer] benchmark task failed: {exc!r}", flush=True)

    _current_task = asyncio.create_task(coro)
    _current_task.add_done_callback(_log_task_failure)
    return {"status": "started", "broker": config.broker, "config": config.config}


@app.post("/stop")
async def stop(sent_count: int = 0) -> dict:
    global _current_task, _sent_count

    _sent_count = sent_count
    if not _current_task or _current_task.done():
        return {"status": "idle"}

    _stop_event.set()
    try:
        await asyncio.wait_for(_current_task, timeout=10.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        _current_task.cancel()

    return {"status": "stopped", "recv_count": _store.recv_count}


@app.get("/metrics")
async def metrics() -> dict:
    if not _run_config:
        raise HTTPException(status_code=400, detail="No run has been started yet")

    return _store.compute(
        sent_count=_sent_count,
        target_rate=_run_config.target_rate,
        msg_size=_run_config.msg_size,
        config=_run_config.config.value,
        broker=_run_config.broker.value,
        duration=_run_config.duration,
    )


@app.get("/status")
async def status() -> dict:
    running = _current_task is not None and not _current_task.done()
    return {"running": running, "recv_count": _store.recv_count}
