from contextlib import contextmanager
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


@contextmanager
def service_errors():
    """Convert service-layer exceptions to HTTP responses."""
    try:
        yield
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="数据冲突，请勿重复操作")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
