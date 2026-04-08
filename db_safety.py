from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def assert_safe_test_database_url(url: str, *, context: str) -> None:
    """Refuse destructive test helpers unless the target DB name ends with `_test`."""
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise RuntimeError(f"{context} requires a valid database URL.") from exc

    backend = parsed.drivername.split("+", 1)[0]
    if backend != "postgresql":
        raise RuntimeError(f"{context} requires a PostgreSQL database URL.")

    database = (parsed.database or "").strip()
    if not database.endswith("_test"):
        raise RuntimeError(
            f"{context} refuses to run against database {database!r}; "
            "target database name must end with '_test'."
        )
