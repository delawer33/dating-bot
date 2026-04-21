import time
from dataclasses import dataclass, field


@dataclass
class MetricsStore:
    """
    Accumulator for a single benchmark run.

    After the first message, ``warmup_seconds`` from that instant are excluded
    from latency samples and from the steady-state throughput denominator.
    Total ``recv_count`` still counts every message (warmup + steady).
    """

    warmup_seconds: float = 0.0
    start_time: float = field(default_factory=time.monotonic)
    recv_count: int = 0
    recv_steady: int = 0
    ack_count: int = 0
    error_count: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    seq_seen: set[int] = field(default_factory=set)
    _first_msg_t0: float | None = None

    def record(self, send_ts: float, seq: int, acked: bool = False) -> None:
        recv_ts = time.monotonic()
        self.recv_count += 1
        self.seq_seen.add(seq)
        if acked:
            self.ack_count += 1

        if self._first_msg_t0 is None:
            self._first_msg_t0 = recv_ts

        in_warmup = (
            self.warmup_seconds > 0
            and (recv_ts - self._first_msg_t0) < self.warmup_seconds
        )
        if in_warmup:
            return

        self.recv_steady += 1
        latency_ms = (recv_ts - send_ts) * 1000.0
        self.latencies_ms.append(latency_ms)

    def record_error(self) -> None:
        self.error_count += 1

    def compute(self, sent_count: int, target_rate: int, msg_size: int, config: str, broker: str, duration: int) -> dict:
        now = time.monotonic()
        elapsed_total = max(now - self.start_time, 0.001)

        if self._first_msg_t0 is None:
            steady_elapsed = elapsed_total
        else:
            steady_elapsed = max(
                now - self._first_msg_t0 - float(self.warmup_seconds),
                0.001,
            )

        throughput = self.recv_steady / steady_elapsed if self.recv_steady else 0.0

        if self.latencies_ms:
            sorted_lats = sorted(self.latencies_ms)
            n = len(sorted_lats)
            avg = sum(sorted_lats) / n
            p95 = sorted_lats[int(n * 0.95)]
            max_lat = sorted_lats[-1]
        else:
            avg = p95 = max_lat = 0.0

        max_seq = max(self.seq_seen) if self.seq_seen else 0
        expected = max_seq + 1 if self.seq_seen else 0
        lost = max(0, expected - len(self.seq_seen))

        return {
            "broker": broker,
            "config": config,
            "msg_size": msg_size,
            "target_rate": target_rate,
            "duration": duration,
            "warmup_seconds": int(self.warmup_seconds),
            "sent_count": sent_count,
            "recv_count": self.recv_count,
            "recv_steady": self.recv_steady,
            "ack_count": self.ack_count,
            "lost_count": lost,
            "error_count": self.error_count,
            "throughput_msg_s": round(throughput, 2),
            "latency_avg_ms": round(avg, 3),
            "latency_p95_ms": round(p95, 3),
            "latency_max_ms": round(max_lat, 3),
        }
