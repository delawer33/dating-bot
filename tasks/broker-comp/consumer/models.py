from enum import Enum

from pydantic import BaseModel, Field, model_validator


class BrokerType(str, Enum):
    rmq = "rmq"
    redis_streams = "redis_streams"


class BrokerConfig(str, Enum):
    durable_ack = "durable_ack"
    inmemory_noack = "inmemory_noack"


class RunConfig(BaseModel):
    broker: BrokerType
    config: BrokerConfig
    target_rate: int = Field(gt=0, description="Target messages per second")
    msg_size: int = Field(gt=0, description="Target message payload size in bytes")
    duration: int = Field(default=60, gt=0, description="Test duration in seconds")
    warmup_seconds: int = Field(
        default=3,
        ge=0,
        description="Ignore this many seconds after first received message for latency and steady throughput",
    )

    @model_validator(mode="after")
    def _warmup_before_duration(self) -> "RunConfig":
        if self.warmup_seconds > 0 and self.warmup_seconds >= self.duration:
            raise ValueError("warmup_seconds must be less than duration")
        return self


class MessagePayload(BaseModel):
    id: str
    send_ts: float
    seq: int
    payload: str


class MetricsResult(BaseModel):
    broker: str
    config: str
    msg_size: int
    target_rate: int
    duration: int
    sent_count: int
    recv_count: int
    ack_count: int
    lost_count: int
    error_count: int
    throughput_msg_s: float
    latency_avg_ms: float
    latency_p95_ms: float
    latency_max_ms: float
