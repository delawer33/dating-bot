# Apache JMeter 5.6 for reproducible CLI runs (host JMeter installs vary widely).
# Build: docker build -t dating-jmeter -f benchmarks/jmeter/Dockerfile benchmarks/jmeter
# Run:  docker run --rm -v "$PWD/benchmarks/jmeter:/bench" -w /bench dating-jmeter \
#          -n -t dating-api-benchmark.jmx -l results/run.jtl -e -o results/html-report \
#          -Japi.host=host.docker.internal -Jbot.secret=your-secret
FROM eclipse-temurin:21-jre-jammy

ARG JMETER_VERSION=5.6.3
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && curl -fsSL "https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz" \
    | tar xz -C /opt \
  && ln -s "/opt/apache-jmeter-${JMETER_VERSION}" /opt/jmeter \
  && apt-get purge -y curl \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/jmeter/bin:${PATH}"

WORKDIR /bench
ENTRYPOINT ["jmeter"]
