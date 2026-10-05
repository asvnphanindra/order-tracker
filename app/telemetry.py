"""OpenTelemetry setup for Order Tracker: metrics, logs, and traces.

OTEL_EXPORTER=console (default) -> print signals to stdout (Question 2)
OTEL_EXPORTER=otlp -> send to the OTel Collector (Question 3+)
"""
from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, ConsoleLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

ORDER_LOOKUP_ROUTE = "/api/orders/{order_id}"

_order_lookup_counter = None


def _exporters():
    """Return (span_exporter, metric_exporter, log_exporter) for the chosen mode."""
    if os.getenv("OTEL_EXPORTER", "console").lower() == "otlp":
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(), OTLPMetricExporter(), OTLPLogExporter()
    return ConsoleSpanExporter(), ConsoleMetricExporter(), ConsoleLogExporter()


def setup_telemetry(app) -> None:
    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "order-tracker")}
    )
    span_exporter, metric_exporter, log_exporter = _exporters()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "5000")),
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(logger_provider)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))

    LoggingInstrumentor().instrument(set_logging_format=True)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/healthz")

    global _order_lookup_counter
    _order_lookup_counter = metrics.get_meter("order-tracker").create_counter(
        "order_tracker_requests",
        description="Order lookup requests",
    )


def record_order_lookup(*, order_id: str, status_code: int) -> None:
    logger = logging.getLogger("order.lookup")
    tracer = trace.get_tracer("order-tracker")
    with tracer.start_as_current_span("order.lookup") as span:
        span.set_attribute("http.route", ORDER_LOOKUP_ROUTE)
        span.set_attribute("http.status_code", status_code)
        span.set_attribute("order.id", order_id)
        logger.info(
            "order lookup order_id=%s http.route=%s http.status_code=%s",
            order_id,
            ORDER_LOOKUP_ROUTE,
            status_code,
        )
        _order_lookup_counter.add(
            1,
            {
                "http.route": ORDER_LOOKUP_ROUTE,
                "http.status_code": str(status_code),
            },
        )
