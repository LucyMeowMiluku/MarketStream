#!/usr/bin/env bash
set -euo pipefail

KAFKA_CONTAINER=$(docker-compose ps -q kafka)

topics=("raw.prices" "raw.news_sentiment" "stream.features" "stream.anomalies")

for topic in "${topics[@]}"; do
  echo "Creating topic: $topic"
  docker exec "$KAFKA_CONTAINER" /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 1 \
    --replication-factor 1
done

echo "All topics created."
docker exec "$KAFKA_CONTAINER" /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
