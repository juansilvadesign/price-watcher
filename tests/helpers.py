from pathlib import Path

from pricewatch.registry import Target

FIXTURE = Path(__file__).parent / "fixtures" / "buyticketbrasil-rockinrio2026-09-04.rsc.txt"


def fixture_body() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def make_target(**over) -> Target:
    base = dict(
        id="t1",
        label="test target",
        adapter="buyticketbrasil",
        params={
            "event_slug": "rockinrio2026",
            "data_millis": 1788570000000,
            "evento_local": "1765323377313x720803947984191500",
            "cidade": "Rio de Janeiro",
        },
        filters={},
        rules={},
        enabled=True,
    )
    base.update(over)
    return Target(**base)
