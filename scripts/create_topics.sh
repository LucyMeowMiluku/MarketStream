#!/usr/bin/env bash
set -euo pipefail

KAFKA_CONTAINER=$(docker-compose ps -q kafka)

topics=(
  "raw.market_events"
  "stream.factor_snapshots"
  "stream.anomalies"
  "raw.prices"
  "raw.news_sentiment"
  "stream.features"
)

for topic in "${topics[@]}"; do
  partitions=1
  if [[ "$topic" == "raw.market_events" || "$topic" == "stream.factor_snapshots" ]]; then
    partitions=5
  fi
  echo "Creating topic: $topic"
  docker exec "$KAFKA_CONTAINER" /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor 1
done

echo "All topics created."
docker exec "$KAFKA_CONTAINER" /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
