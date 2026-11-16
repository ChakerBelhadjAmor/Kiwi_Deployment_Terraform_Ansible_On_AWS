from pathlib import Path
from types import SimpleNamespace as NS

from import_requirements import publish_requirements, read_markdown
from import_xlsx import KiwiRpcClient


class FakeClient:
    def __init__(self):
        self.calls = []

    def ensure_plan(self, product, plan_name):
        self.calls.append(("ensure_plan", product, plan_name))
        return 42

    def set_plan_text(self, plan_id, text):
        self.calls.append(("set_plan_text", plan_id, text))


def test_publish_requirements_creates_plan_then_sets_text():
    client = FakeClient()
    publish_requirements(client, "Budget Tracker", "Exigences", "| ID |\n| BF-01 |")
    assert client.calls == [
        ("ensure_plan", "Budget Tracker", "Exigences"),
        ("set_plan_text", 42, "| ID |\n| BF-01 |"),
    ]


def test_read_markdown_keeps_accents_and_tables(tmp_path: Path):
    f = tmp_path / "e.md"
    f.write_text("| BF-01 | Gestion utilisateur | Créer un compte |\n", encoding="utf-8")
    assert "Créer un compte" in read_markdown(f)


def test_kiwi_client_set_plan_text_updates_the_plan():
    seen = []
    rpc = NS(TestPlan=NS(update=lambda pid, vals: seen.append((pid, vals))))
    KiwiRpcClient(rpc=rpc).set_plan_text(7, "texte")
    assert seen == [(7, {"text": "texte"})]


def test_requirements_plans_get_the_product_type_not_an_arbitrary_one():
    types = [{"id": 1, "name": "Unit"}, {"id": 8, "name": "Product"}]
    rpc = NS(PlanType=NS(filter=lambda q: [t for t in types if t["name"] == q["name"]] if q else types))
    client = KiwiRpcClient(rpc=rpc)
    assert client._plan_type_id("Besoin fonctionnel") == 8
    assert client._plan_type_id("Besoin non fonctionnel") == 8
