from contextlib import contextmanager
from fastapi import HTTPException


@contextmanager
def service_errors():
    """Convert service-layer exceptions to HTTP responses."""
    try:
        yield
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
