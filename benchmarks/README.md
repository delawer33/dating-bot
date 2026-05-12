# Benchmarks

Load and performance tooling for the dating-bot HTTP API.

| Path | Purpose |
|------|---------|
| `jmeter/` | JMeter 5.6 image, `generate_jmx.py`, realistic multi-route plan, `viewers.csv` |
| `../backend/scripts/seed_benchmark_discovery_users.py` | Seeds registered users; optional `--write-viewers-csv` from host |

See `jmeter/README.md` for the full scenario (health + profile + inbox + next + like/skip), Compose network run, and tunables.
