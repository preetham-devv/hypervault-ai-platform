# Observability package — logging, tracing, and metrics for HyperVault.
#
# Initialisation order (called from src/api/main.py lifespan):
#   1. configure_logging()  — structlog JSON/console setup
#   2. setup_tracing(engine) — OTel TracerProvider + SQLAlchemy instrumentation
#   3. setup_metrics()       — OTel MeterProvider + instrument registration
