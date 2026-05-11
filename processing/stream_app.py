from datetime import timedelta

from quixstreams import Application

from config.logging_config import get_logger
from config.settings import settings
from processing.feature_engine import compute_window_features

log = get_logger("stream_processor")


def window_reducer(agg: dict, value: dict) -> dict:
    agg["prices"].append(value["close"])
    agg["volumes"].append(value["volume"])
    agg["ticker"] = value["ticker"]
    return agg


def window_initializer(value: dict) -> dict:
    return {
        "ticker": value["ticker"],
        "prices": [value["close"]],
        "volumes": [value["volume"]],
    }


def main():
    app = Application(
        broker_address=settings.kafka_bootstrap_servers,
        consumer_group="stream-processor",
        auto_offset_reset="latest",
        auto_create_topics=True,
    )

    prices_topic = app.topic("raw.prices", value_deserializer="json")
    features_topic = app.topic("stream.features", value_serializer="json")

    sdf = app.dataframe(prices_topic)

    sdf_windowed = (
        sdf.tumbling_window(
            duration_ms=timedelta(minutes=settings.window_duration_minutes),
            grace_ms=timedelta(seconds=30),
        )
        .reduce(reducer=window_reducer, initializer=window_initializer)
        .final()
    )

    def build_features(row: dict) -> dict:
        window_value = row["value"]
        features = compute_window_features(
            window_value=window_value,
            ticker=window_value["ticker"],
            window_start=row["start"],
            window_end=row["end"],
        )
        log.info(
            "window_features",
            ticker=features["ticker"],
            price_change=features["price_change_rate"],
            volume=features["total_volume"],
        )
        return features

    sdf_windowed = sdf_windowed.apply(build_features)
    sdf_windowed.to_topic(features_topic)

    log.info("starting_stream_processor", window_minutes=settings.window_duration_minutes)
    app.run()


if __name__ == "__main__":
    main()
