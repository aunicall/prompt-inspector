"""
Import sensitive words from an Excel file into the sensitive_words table.

Excel columns: Category, MatchType, Word, Description
Used columns: Word, MatchType, Description

Usage:
    python -m scripts.import_sensitive_words <excel_file_path>

Example:
    python -m scripts.import_sensitive_words data/sensitive_words.xlsx
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl
from sqlalchemy import select
from app.database import async_session, init_db
from app.models.sensitive_word import SensitiveWord

VALID_MATCH_TYPES = {"literal", "pattern"}


async def import_from_excel(file_path: str):
    """Read Excel and import into sensitive_words table."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    if path.suffix.lower() not in (".xls", ".xlsx"):
        print(f"Error: Unsupported file format: {path.suffix}. Use .xls or .xlsx")
        sys.exit(1)

    wb = openpyxl.load_workbook(str(path), read_only=True)
    ws = wb.active

    rows = []
    first_row = True
    for row in ws.iter_rows(values_only=True):
        if first_row:
            first_row = False
            print(f"Header: {row}")
            continue
        if not row or len(row) < 3:
            continue

        # Columns: Category, MatchType, Word, Description
        match_type = str(row[1]).strip().lower() if row[1] else "literal"
        word = str(row[2]).strip() if row[2] else ""
        description = str(row[3]).strip() if len(row) > 3 and row[3] else None

        if not word:
            continue
        if match_type not in VALID_MATCH_TYPES:
            print(f"Warning: Invalid match_type '{match_type}' for '{word}', defaulting to 'literal'")
            match_type = "literal"

        rows.append((word, match_type, description))

    wb.close()
    print(f"Parsed {len(rows)} valid rows from Excel.")

    if not rows:
        print("No data to import.")
        return

    await init_db()

    async with async_session() as db:
        result = await db.execute(select(SensitiveWord.word))
        existing_words = {r[0].lower() for r in result.all()}

        imported = 0
        duplicates = 0
        for word, match_type, description in rows:
            if word.lower() in existing_words:
                duplicates += 1
                continue
            db.add(SensitiveWord(
                word=word,
                match_type=match_type,
                description=description,
            ))
            existing_words.add(word.lower())
            imported += 1

        await db.commit()

    print(f"Import complete: {imported} imported, {duplicates} duplicates skipped, {len(rows)} total.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.import_sensitive_words <excel_file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    asyncio.run(import_from_excel(file_path))


if __name__ == "__main__":
    main()
