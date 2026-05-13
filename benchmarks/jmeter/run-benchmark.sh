#!/usr/bin/env bash
# Run the dating-api JMeter plan in Docker. Requires a seeded DB (see README).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/results"
IMAGE="${JMETER_IMAGE:-alpine/jmeter:latest}"
STAMP="$(date +%Y%m%d-%H%M%S)"
# Paths inside the container (mount is /t)
JTL_IN="/t/results/run-${STAMP}.jtl"
REPORT_IN="/t/results/report-${STAMP}"
REPORT_HOST="${RESULTS_DIR}/report-${STAMP}"

mkdir -p "${RESULTS_DIR}"

if [[ -z "${BOT_SECRET:-}" ]]; then
  echo "Set BOT_SECRET to the same value as backend BOT_SECRET (e.g. export BOT_SECRET=change-me-in-production)" >&2
  exit 1
fi

echo "Using image: ${IMAGE}"
echo "Results: ${RESULTS_DIR}/run-${STAMP}.jtl"
echo "HTML report: ${REPORT_HOST}"

# JMeter runs in a container: "localhost" there is not the host. On Linux, --network host fixes that.
DOCKER_NET=()
_h="${HOST:-localhost}"
if [[ "${OSTYPE:-}" == linux-gnu* || "${OSTYPE:-}" == linux-musl* ]]; then
  if [[ "${_h}" == "localhost" || "${_h}" == "127.0.0.1" ]]; then
    DOCKER_NET=(--network host)
    echo "Using Docker --network host so JMeter can reach API on ${_h}:${PORT:-8000}"
  fi
fi

docker run --rm "${DOCKER_NET[@]}" \
  -v "${SCRIPT_DIR}:/t" \
  -w /t \
  "${IMAGE}" \
  -n \
  -t dating-api-benchmark.jmx \
  -JBOT_SECRET="${BOT_SECRET}" \
  -JHOST="${HOST:-localhost}" \
  -JPORT="${PORT:-8000}" \
  -JPROTOCOL="${PROTOCOL:-http}" \
  -Jthreads="${THREADS:-30}" \
  -Jrampup="${RAMPUP:-120}" \
  -Jduration="${DURATION:-300}" \
  -Jcsv="${CSV:-viewers.csv}" \
  -l "${JTL_IN}" \
  -e -o "${REPORT_IN}"

echo "Done. Open ${REPORT_HOST}/index.html in a browser."
