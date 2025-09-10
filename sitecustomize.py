# sitecustomize.py
# Auto-imported by Python if present on sys.path.
try:
    from http_trace import enable_tracing_if_requested
    enable_tracing_if_requested()
except Exception:
    # Don't break the app if tracing fails.
    pass
