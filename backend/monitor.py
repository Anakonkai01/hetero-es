"""Stable desktop monitor command and shared telemetry observation type."""

from .apps.monitor import main as main, TelemetrySampler as TelemetrySampler

if __name__ == "__main__":
    raise SystemExit(main())
