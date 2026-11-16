"""Import Budget Tracker test-case workbooks (.xlsx) into Kiwi TCMS.

Workbook layout (all case sheets share it): a header row whose first cell is
"ID" (row 5 or 9, depending on the sheet), followed by one test case per row.
Sheets without such a header ("Mode d'emploi", "Récapitulatif", ...) are skipped.

Mapping to Kiwi:
  sheet name              -> Test Plan (one per sheet, typed from the level)
  ID + "Contexte de test" -> TestCase.summary ("CP-01 - UserService.createUser ...")
  Données/Pré/Post/Attendu-> TestCase.text (Markdown sections)
  Priorité                -> Priority (Haute=P1, Moyenne=P3, Basse=P5)
  Exigence liée           -> tag on the case (e.g. BF-01)
  Product                 -> --product (created on demand), version "unspecified"

Credentials come from ~/.tcms.conf (never from arguments or this repo).
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import openpyxl

PRIORITY_MAP = {"haute": "P1", "moyenne": "P3", "basse": "P5"}
PLAN_TYPE_MAP = {
    "composant": "Unit",
    "intégration": "Integration",
    "integration": "Integration",
    "système": "System",
    "systeme": "System",
    "scénarios": "Acceptance",
    "scenarios": "Acceptance",
}
SUMMARY_MAX = 255


@dataclass(frozen=True)
class TestCaseRow:
    __test__ = False  # not a pytest class

    case_id: str
    plan: str
    test_type: str
    priority: str
    requirement: str
    context: str
    data: str
    precondition: str
    postcondition: str
    expected: str

    @property
    def summary(self) -> str:
        return f"{self.case_id} - {self.context}"[:SUMMARY_MAX]

    @property
    def text(self) -> str:
        return (
            f"**Type:** {self.test_type}\n\n"
            f"**Exigence liée:** {self.requirement}\n\n"
            f"### Données de test\n{self.data}\n\n"
            f"### Pré-condition\n{self.precondition}\n\n"
            f"### Post-condition\n{self.postcondition}\n\n"
            f"### Résultat attendu\n{self.expected}\n"
        )

    @property
    def kiwi_priority(self) -> str:
        return PRIORITY_MAP.get(self.priority.lower(), "P3")


@dataclass(frozen=True)
class ImportReport:
    created: int
    skipped: int
    errors: int


class KiwiClient(Protocol):
    def ensure_plan(self, product: str, plan_name: str) -> int: ...
    def case_exists(self, plan_id: int, summary: str) -> bool: ...
    def create_case(self, plan_id: int, row: TestCaseRow) -> None: ...


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def _header_key(value) -> str:
    return _clean(value).split("\n")[0].strip().lower()


def load_cases(path: Path) -> list[TestCaseRow]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows: list[TestCaseRow] = []
    for ws in wb.worksheets:
        header_idx: dict[str, int] | None = None
        for raw in ws.iter_rows(values_only=True):
            if header_idx is None:
                if raw and _header_key(raw[0]) == "id":
                    header_idx = {_header_key(c): i for i, c in enumerate(raw) if c}
                continue
            def col(name: str) -> str:
                i = header_idx.get(name)
                return _clean(raw[i]) if i is not None and i < len(raw) else ""
            case_id = col("id")
            if not case_id:
                continue
            rows.append(
                TestCaseRow(
                    case_id=case_id,
                    plan=ws.title,
                    test_type=col("type de test"),
                    priority=col("priorité"),
                    requirement=col("exigence liée"),
                    context=col("contexte de test"),
                    data=col("données de test"),
                    precondition=col("pré-condition"),
                    postcondition=col("post-condition"),
                    expected=col("résultat attendu"),
                )
            )
    return rows


def import_cases(
    rows: list[TestCaseRow], client: KiwiClient, product: str, dry_run: bool, max_errors: int = 10
) -> ImportReport:
    created = skipped = errors = 0
    seen: set[tuple[str, str]] = set()
    plan_ids: dict[str, int] = {}
    for row in rows:
        key = (row.plan, row.case_id)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        if dry_run:
            created += 1
            continue
        try:
            if row.plan not in plan_ids:
                plan_ids[row.plan] = client.ensure_plan(product, row.plan)
            plan_id = plan_ids[row.plan]
            if client.case_exists(plan_id, row.summary):
                skipped += 1
                continue
            client.create_case(plan_id, row)
            created += 1
        except Exception as exc:  # keep going; report at the end
            print(f"ERROR {row.case_id}: {exc}", file=sys.stderr)
            errors += 1
            if errors >= max_errors:
                print(f"Aborting after {errors} errors", file=sys.stderr)
                break
    return ImportReport(created=created, skipped=skipped, errors=errors)


class KiwiRpcClient:
    """Thin adapter over tcms_api.TCMS (credentials from ~/.tcms.conf)."""

    def __init__(self, rpc=None) -> None:
        if rpc is None:
            from tcms_api import TCMS

            rpc = TCMS().exec
        self.rpc = rpc
        self._product: dict | None = None
        self._category: int | None = None

    def _ensure_product(self, name: str) -> dict:
        if self._product and self._product["name"] == name:
            return self._product
        found = self.rpc.Product.filter({"name": name})
        if found:
            product = found[0]
        else:
            classification = (self.rpc.Classification.filter({}) or [None])[0]
            if classification is None:
                classification = self.rpc.Classification.create({"name": "Default"})
            product = self.rpc.Product.create(
                {"name": name, "classification": classification["id"], "description": "Imported from xlsx"}
            )
        self._product = product
        return product

    def _version_id(self, product_id: int) -> int:
        found = self.rpc.Version.filter({"product": product_id})
        if found:
            return found[0]["id"]
        return self.rpc.Version.create({"product": product_id, "value": "unspecified"})["id"]

    def _plan_type_id(self, plan_name: str) -> int:
        wanted = PLAN_TYPE_MAP.get(plan_name.lower(), "Functionality")
        found = self.rpc.PlanType.filter({"name": wanted}) or self.rpc.PlanType.filter({})
        return found[0]["id"]

    def ensure_plan(self, product: str, plan_name: str) -> int:
        prod = self._ensure_product(product)
        found = self.rpc.TestPlan.filter({"name": plan_name, "product": prod["id"]})
        if found:
            return found[0]["id"]
        plan = self.rpc.TestPlan.create(
            {
                "name": plan_name,
                "text": f"Imported from xlsx sheet '{plan_name}'",
                "product": prod["id"],
                "product_version": self._version_id(prod["id"]),
                "type": self._plan_type_id(plan_name),
                "is_active": True,
            }
        )
        return plan["id"]

    def case_exists(self, plan_id: int, summary: str) -> bool:
        return bool(self.rpc.TestCase.filter({"plan": plan_id, "summary": summary}))

    def create_case(self, plan_id: int, row: TestCaseRow) -> None:
        prod = self._product
        # A previous run may have created the case but failed before linking it
        # to the plan: reuse it instead of creating a duplicate.
        found = self.rpc.TestCase.filter({"summary": row.summary, "category__product": prod["id"]})
        if found:
            case_id = found[0]["id"]
        else:
            if self._category is None:
                self._category = self.rpc.Category.filter({"product": prod["id"]})[0]["id"]
            priority = self.rpc.Priority.filter({"value": row.kiwi_priority})[0]["id"]
            status = self.rpc.TestCaseStatus.filter({"name": "CONFIRMED"})[0]["id"]
            case_id = self.rpc.TestCase.create(
                {
                    "summary": row.summary,
                    "text": row.text,
                    "category": self._category,
                    "priority": priority,
                    "case_status": status,
                    "product": prod["id"],
                }
            )["id"]
        if not self.rpc.TestCase.filter({"plan": plan_id, "id": case_id}):
            self.rpc.TestPlan.add_case(plan_id, case_id)
        if row.requirement:
            self.rpc.TestCase.add_tag(case_id, row.requirement)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if os.environ.get("KIWI_INSECURE_TLS") == "1":  # LOCAL TESTING ONLY (self-signed cert)
        import ssl

        ssl._create_default_https_context = ssl._create_unverified_context
        print("WARNING: TLS verification disabled", file=sys.stderr)

    rows = [r for f in args.files for r in load_cases(f)]
    client = None if args.dry_run else KiwiRpcClient()
    report = import_cases(rows, client, args.product, args.dry_run)
    mode = "DRY RUN" if args.dry_run else "IMPORT"
    print(f"{mode}: created={report.created} skipped={report.skipped} errors={report.errors}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
