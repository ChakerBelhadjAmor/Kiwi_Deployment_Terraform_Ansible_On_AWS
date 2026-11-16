from pathlib import Path

import openpyxl
import pytest

from import_xlsx import ImportReport, TestCaseRow, import_cases, load_cases

HEADER = [
    "ID", "Type de test", "Priorité", "Exigence liée", "Contexte de test\n(éléments)",
    "Données de test\n(inputs)", "Pré-condition", "Post-condition", "Résultat attendu",
    "Résultat obtenu", "Statut", "Observation", "Mesure corrective",
]


def make_workbook(path: Path, rows, sheet="Composant"):
    wb = openpyxl.Workbook()
    wb.active.title = "Mode d'emploi"
    wb.active["A1"] = "notes only"
    ws = wb.create_sheet(sheet)
    ws["A1"] = "TITRE"
    ws["A3"] = "PROJET"
    for col, name in enumerate(HEADER, 1):
        ws.cell(row=5, column=col, value=name)
    for r, row in enumerate(rows, 6):
        for col, value in enumerate(row, 1):
            ws.cell(row=r, column=col, value=value)
    wb.create_sheet("Récapitulatif")["A1"] = "summary"
    wb.save(path)
    return path


def case(cid="CP-01", **kw):
    row = [cid, "Fonctionnel", "Haute", "BF-01", "Création utilisateur", "données", "pré", "post",
           "attendu", None, "Non exécuté", None, None]
    for key, idx in kw.items():
        row[int(key[1:])] = idx
    return row


class FakeClient:
    def __init__(self, existing=()):
        self.calls = []
        self.existing = set(existing)

    def ensure_plan(self, product, plan_name):
        self.calls.append(("ensure_plan", plan_name))
        return 1

    def case_exists(self, plan_id, summary):
        self.calls.append(("case_exists", summary))
        return summary in self.existing

    def create_case(self, plan_id, row):
        self.calls.append(("create_case", row.case_id))


def test_load_cases_skips_blank_rows(tmp_path):
    f = make_workbook(tmp_path / "a.xlsx", [case("CP-01"), [None] * 13, case("CP-02")])
    assert [r.case_id for r in load_cases(f)] == ["CP-01", "CP-02"]


def test_load_cases_ignores_sheets_without_id_header(tmp_path):
    f = make_workbook(tmp_path / "a.xlsx", [case()])
    rows = load_cases(f)
    assert len(rows) == 1 and rows[0].plan == "Composant"


def test_load_cases_preserves_accents(tmp_path):
    f = make_workbook(tmp_path / "a.xlsx", [case(c4="Création « ons.chebel » à vérifier")])
    assert load_cases(f)[0].context == "Création « ons.chebel » à vérifier"


def test_load_cases_strips_whitespace_and_maps_priority(tmp_path):
    f = make_workbook(tmp_path / "a.xlsx", [case("  CP-09 ", c2="Moyenne", c8="  ok  ")])
    r = load_cases(f)[0]
    assert (r.case_id, r.priority, r.expected) == ("CP-09", "Moyenne", "ok")


def test_import_cases_dry_run_makes_no_api_calls():
    client = FakeClient()
    rows = [TestCaseRow("CP-01", "Composant", "t", "Haute", "BF-01", "c", "d", "p", "q", "e")]
    report = import_cases(rows, client, "Budget Tracker", dry_run=True)
    assert client.calls == []
    assert report == ImportReport(created=1, skipped=0, errors=0)


def test_import_cases_dedupes_ids_within_plan():
    client = FakeClient()
    row = TestCaseRow("CP-01", "Composant", "t", "Haute", "BF-01", "c", "d", "p", "q", "e")
    report = import_cases([row, row], client, "Budget Tracker", dry_run=False)
    assert report.created == 1 and report.skipped == 1
    assert [c for c in client.calls if c[0] == "create_case"] == [("create_case", "CP-01")]


def test_import_report_counts_existing_as_skipped():
    row = TestCaseRow("CP-01", "Composant", "t", "Haute", "BF-01", "c", "d", "p", "q", "e")
    client = FakeClient(existing={row.summary})
    report = import_cases([row], client, "Budget Tracker", dry_run=False)
    assert report == ImportReport(created=0, skipped=1, errors=0)


def test_import_cases_counts_errors_and_continues():
    class Boom(FakeClient):
        def create_case(self, plan_id, row):
            if row.case_id == "CP-01":
                raise RuntimeError("api down")
            super().create_case(plan_id, row)

    rows = [TestCaseRow(i, "Composant", "t", "Haute", "BF", "c", "d", "p", "q", "e") for i in ("CP-01", "CP-02")]
    report = import_cases(rows, Boom(), "Budget Tracker", dry_run=False)
    assert report == ImportReport(created=1, skipped=0, errors=1)
