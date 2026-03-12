from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from config import settings

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

OPTIONAL_COLUMNS = {
    "part": {
        "image": "TEXT",
    },
    "jewelry": {
        "image": "TEXT",
    },
}


def ensure_optional_columns() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table_name, columns in OPTIONAL_COLUMNS.items():
            if table_name not in table_names:
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue
                conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}'))


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
