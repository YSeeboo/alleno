from datetime import datetime

from services.plating_export import build_export_filename


def test_build_export_filename_with_receipt_code_appends_it():
    created = datetime(2026, 5, 24, 10, 0)
    name = build_export_filename("珠岛手工", created, "pdf", receipt_code="PHYY8")
    assert name == "发出_珠岛手工_260524_PHYY8.pdf"


def test_build_export_filename_without_receipt_code_unchanged():
    created = datetime(2026, 5, 24, 10, 0)
    name = build_export_filename("珠岛手工", created, "pdf")
    assert name == "发出_珠岛手工_260524.pdf"


def test_build_export_filename_with_none_receipt_code_unchanged():
    created = datetime(2026, 5, 24, 10, 0)
    name = build_export_filename("珠岛手工", created, "pdf", receipt_code=None)
    assert name == "发出_珠岛手工_260524.pdf"


def test_build_export_filename_with_blank_receipt_code_unchanged():
    created = datetime(2026, 5, 24, 10, 0)
    name = build_export_filename("珠岛手工", created, "pdf", receipt_code="   ")
    assert name == "发出_珠岛手工_260524.pdf"
