"""Serialize a generated report's rows to CSV / XLSX / PDF (Phase 8; TRD §12).

CSV is stdlib. XLSX and PDF each need a library to be correct on escaping,
zip/PDF structure, and pagination — openpyxl and reportlab are the standard
choices, so we lean on them rather than hand-rolling either format.
"""

import csv
import io

MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def render(fmt: str, columns: list[str], rows: list[dict]) -> bytes:
    if fmt == "csv":
        return _csv(columns, rows)
    if fmt == "xlsx":
        return _xlsx(columns, rows)
    if fmt == "pdf":
        return _pdf(columns, rows)
    raise ValueError(f"Unsupported format: {fmt}")


def _cell(value) -> str:
    return "" if value is None else str(value)


def _csv(columns: list[str], rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _xlsx(columns: list[str], rows: list[dict]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append([row.get(col) for col in columns])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _pdf(columns: list[str], rows: list[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    data = [columns] + [[_cell(row.get(col)) for col in columns] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    doc.build([table])
    return buffer.getvalue()
