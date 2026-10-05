import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
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

_resource = Resource.create({"service.name": "order-tracker"})
_order_lookup_counter = None


def _use_console() -> bool:
    return os.getenv("OTEL_EXPORTER", "console").lower() == "console"


def _otlp_endpoint() -> str:
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")


def setup_telemetry(app) -> None:
    if _use_console():
        trace_provider = TracerProvider(resource=_resource)
        trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        metric_readers = [
            PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=1000)
        ]
    else:
        trace_provider = TracerProvider(resource=_resource)
        trace_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=_otlp_endpoint(), insecure=True))
        )
        metric_readers = [
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=_otlp_endpoint(), insecure=True),
                export_interval_millis=5000,
            )
        ]

    trace.set_tracer_provider(trace_provider)
    metrics.set_meter_provider(MeterProvider(resource=_resource, metric_readers=metric_readers))

    log_provider = LoggerProvider(resource=_resource)
    if _use_console():
        log_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogExporter()))
    else:
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=_otlp_endpoint(), insecure=True))
        )
    set_logger_provider(log_provider)

    root = logging.getLogger()
    root.addHandler(LoggingHandler(level=logging.INFO, logger_provider=log_provider))
    root.setLevel(logging.INFO)

    LoggingInstrumentor().instrument(set_logging_format=True)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/healthz")

    global _order_lookup_counter
    _order_lookup_counter = metrics.get_meter("order-tracker").create_counter(
        "http.server.requests",
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
            "order lookup",
            extra={
                "order_id": order_id,
                "http.route": ORDER_LOOKUP_ROUTE,
                "http.status_code": status_code,
            },
        )
        _order_lookup_counter.add(
            1,
            {"http.route": ORDER_LOOKUP_ROUTE, "http.status_code": status_code},
        )
