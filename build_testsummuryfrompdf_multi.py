#!/usr/bin/env python3
"""Build a combined income/expense workbook from three uploaded PDF statements."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from pypdf import PdfReader


@dataclass
class StatementResult:
    name: str
    incomes: dict[str, Decimal]
    expenses: dict[str, Decimal]
    tx_count: int

    @property
    def income_total(self) -> Decimal:
        return sum(self.incomes.values(), start=Decimal("0"))

    @property
    def expense_total(self) -> Decimal:
        return sum(self.expenses.values(), start=Decimal("0"))

    @property
    def net(self) -> Decimal:
        return self.income_total - self.expense_total


AMOUNT_RE = re.compile(r"^([+-])(\d{1,3}(?:\.\d{3})*,\d{2})EUR$")
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
PAGE_RE = re.compile(r"^Seite\d+von\d+$")
IBAN_ONLY_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{8,}$")


def parse_de_amount(value: str) -> Decimal:
    return Decimal(value.replace(".", "").replace(",", "."))


def normalize_line(line: str) -> str:
    """Collapse OCR-style 'F i l e r' lines to 'Filer'."""
    line = line.strip()
    if not line:
        return ""

    tokens = line.split()
    if len(tokens) >= 6:
        single_ratio = sum(1 for token in tokens if len(token) == 1) / len(tokens)
        if single_ratio > 0.7:
            return "".join(tokens)
    return line


def is_meta_line(line: str) -> bool:
    if not line:
        return True
    if line.startswith("Filterparameter"):
        return True
    if line.startswith("BICGENODED"):
        return True
    if line.startswith("IBANDE") and "Uhrzeit" in line:
        return True
    if line.startswith("Kontoinhaber"):
        return True
    if line == "Umsätze":
        return True
    if PAGE_RE.match(line):
        return True
    if line.startswith("WirmachendenWegfrei"):
        return True
    if line.startswith("EUR+") and ("Endsaldo" in line or "Startsaldo" in line):
        return True
    return False


def is_label_noise(line: str) -> bool:
    if not line:
        return True
    if DATE_RE.match(line):
        return True
    if line.startswith("Valuta"):
        return True
    if IBAN_ONLY_RE.match(line):
        return True
    if line.startswith("BIC:"):
        return True
    if "IBAN:" in line:
        return True
    if re.fullmatch(r"[0-9]+", line):
        return True
    return False


def choose_label(block_lines: list[str]) -> str:
    for line in block_lines:
        if line.startswith("Abschluss"):
            return "Abschluss"

    for line in block_lines:
        if not is_label_noise(line):
            return line
    return "Unbekannt"


def parse_statement(pdf_path: str, statement_name: str) -> StatementResult:
    reader = PdfReader(pdf_path)
    income_totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    expense_totals: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    tx_count = 0
    current_block: list[str] = []

    for page in reader.pages:
        raw_lines = (page.extract_text() or "").splitlines()
        for raw_line in raw_lines:
            line = normalize_line(raw_line)
            if is_meta_line(line):
                continue

            amount_match = AMOUNT_RE.match(line)
            if amount_match:
                sign, amount_text = amount_match.groups()
                label = choose_label(current_block)
                amount = parse_de_amount(amount_text)
                if sign == "+":
                    income_totals[label] += amount
                else:
                    expense_totals[label] += amount
                tx_count += 1
                current_block = []
                continue

            if line.startswith("Valuta"):
                continue
            if DATE_RE.match(line):
                current_block = []
                continue

            current_block.append(line)

    return StatementResult(
        name=statement_name,
        incomes=dict(income_totals),
        expenses=dict(expense_totals),
        tx_count=tx_count,
    )


def write_grouped_sheet(ws, sheet_title: str, grouped: dict[str, Decimal]) -> Decimal:
    ws.title = sheet_title
    ws["A1"] = "Name (DE)"
    ws["B1"] = "Amount"
    ws["A1"].font = Font(bold=True)
    ws["B1"].font = Font(bold=True)

    row = 2
    total = Decimal("0")
    for name, amount in sorted(grouped.items(), key=lambda item: (-item[1], item[0].lower())):
        ws.cell(row=row, column=1, value=name)
        amount_cell = ws.cell(row=row, column=2, value=float(amount))
        amount_cell.number_format = "#,##0.00"
        total += amount
        row += 1

    ws.cell(row=row, column=1, value="TOTAL").font = Font(bold=True)
    total_cell = ws.cell(row=row, column=2, value=float(total))
    total_cell.font = Font(bold=True)
    total_cell.number_format = "#,##0.00"

    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 16
    return total


def write_summary_sheet(ws, results: list[StatementResult]) -> None:
    ws.title = "Summary"
    ws["A1"] = "Statement"
    ws["B1"] = "Income total"
    ws["C1"] = "Expense total"
    ws["D1"] = "Net"
    ws["E1"] = "Transactions"
    for col in ("A1", "B1", "C1", "D1", "E1"):
        ws[col].font = Font(bold=True)

    row = 2
    all_income = Decimal("0")
    all_expense = Decimal("0")
    all_tx = 0
    for result in results:
        ws.cell(row=row, column=1, value=result.name)
        ws.cell(row=row, column=2, value=float(result.income_total)).number_format = "#,##0.00"
        ws.cell(row=row, column=3, value=float(result.expense_total)).number_format = "#,##0.00"
        ws.cell(row=row, column=4, value=float(result.net)).number_format = "#,##0.00"
        ws.cell(row=row, column=5, value=result.tx_count)
        all_income += result.income_total
        all_expense += result.expense_total
        all_tx += result.tx_count
        row += 1

    ws.cell(row=row, column=1, value="TOTAL").font = Font(bold=True)
    income_total_cell = ws.cell(row=row, column=2, value=float(all_income))
    expense_total_cell = ws.cell(row=row, column=3, value=float(all_expense))
    net_total_cell = ws.cell(row=row, column=4, value=float(all_income - all_expense))
    tx_total_cell = ws.cell(row=row, column=5, value=all_tx)
    for cell in (income_total_cell, expense_total_cell, net_total_cell, tx_total_cell):
        cell.font = Font(bold=True)
    income_total_cell.number_format = "#,##0.00"
    expense_total_cell.number_format = "#,##0.00"
    net_total_cell.number_format = "#,##0.00"

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 14


def main() -> None:
    sources = [
        ("Mietkonto_2025", "/home/ubuntu/.cursor/projects/workspace/uploads/Ko_ln_Mietkonto_2025__1_.pdf"),
        ("Kaution_2025", "/home/ubuntu/.cursor/projects/workspace/uploads/Ko_ln_Kaution_2025.pdf"),
        ("Girokonto_2025", "/home/ubuntu/.cursor/projects/workspace/uploads/Ko_ln_Girokonto_2025.pdf"),
    ]

    results: list[StatementResult] = []
    all_incomes: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    all_expenses: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for statement_name, pdf_path in sources:
        result = parse_statement(pdf_path, statement_name)
        results.append(result)
        for label, amount in result.incomes.items():
            all_incomes[label] += amount
        for label, amount in result.expenses.items():
            all_expenses[label] += amount

    wb = Workbook()
    summary_ws = wb.active
    write_summary_sheet(summary_ws, results)

    for result in results:
        income_sheet_name = f"{result.name[:18]}_Inc"
        expense_sheet_name = f"{result.name[:18]}_Exp"
        write_grouped_sheet(wb.create_sheet(income_sheet_name), income_sheet_name, result.incomes)
        write_grouped_sheet(wb.create_sheet(expense_sheet_name), expense_sheet_name, result.expenses)

    write_grouped_sheet(wb.create_sheet("All_Incomes"), "All_Incomes", dict(all_incomes))
    write_grouped_sheet(wb.create_sheet("All_Expenses"), "All_Expenses", dict(all_expenses))

    output_path = Path("/workspace/testsummuryfrompdf_multi.xlsx")
    wb.save(output_path)
    print(f"Created {output_path}")
    for result in results:
        print(
            f"{result.name}: tx={result.tx_count}, "
            f"income={result.income_total}, expense={result.expense_total}, net={result.net}"
        )


if __name__ == "__main__":
    main()
