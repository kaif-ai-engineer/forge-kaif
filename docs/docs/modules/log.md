# Logging Module

`forge.log` — Structured JSON logging with automatic trace context propagation.

## Overview

The Log module provides production-ready structured logging that works out of the box.
In production, it outputs JSON for log aggregators. In development, it uses colorized
human-readable output. Trace IDs propagate automatically across async boundaries via
`contextvars`.

## Installation

```bash
pip install forge-runtime
```

## Quick Start

```python
from forge.log import get

logger = get("my_app")
logger.info("Server starting", port=8080)
# {"timestamp": "...", "level": "INFO", "module": "my_app", "message": "Server starting", "port": 8080}
```

## Key Features

### Log Context Binding

```python
from forge.log import context

with context(request_id="abc-123", user_id=42):
    logger.info("Processing request")
    # All log entries within this context include request_id and user_id
```

### Module-Aware Loggers

```python
logger = get("my_app.database")
logger.error("Connection failed", db_host="prod-db-1")
```

### JSON Output (Production)

```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "INFO",
  "module": "my_app",
  "message": "Request completed",
  "trace_id": "abc-123-def-456",
  "duration_ms": 245
}
```

### Development Output

```
[10:30:00] INFO     my_app        Request completed              duration_ms=245 trace_id=abc-123
```

## API Reference

::: forge.log
    options:
      show_root_heading: false
      show_bases: false
      show_source: false
