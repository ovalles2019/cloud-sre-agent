"""Cost Explorer prior-window comparison tests."""

from datetime import date

from backend.config import get_settings
from backend.tools.cost_explorer import CostExplorerTool, equivalent_windows


class FakeCE:
    def __init__(self, current_amount: str, prior_amount: str) -> None:
        self.current_amount = current_amount
        self.prior_amount = prior_amount
        self.calls: list[dict] = []

    def get_cost_and_usage(self, **kwargs):
        self.calls.append(kwargs)
        start = kwargs["TimePeriod"]["Start"]
        current_start, _, _, _ = equivalent_windows()
        amount = self.current_amount if start == current_start.isoformat() else self.prior_amount
        grouped = "GroupBy" in kwargs
        if grouped:
            return {
                "ResultsByTime": [
                    {
                        "Groups": [
                            {
                                "Keys": ["Amazon EC2"],
                                "Metrics": {"UnblendedCost": {"Amount": amount}},
                            }
                        ]
                    }
                ]
            }
        return {
            "ResultsByTime": [
                {"Total": {"UnblendedCost": {"Amount": amount}}}
            ]
        }


def test_flat_spend_is_not_an_anomaly():
    tool = CostExplorerTool(get_settings())
    tool._client = FakeCE("100", "100")
    assert tool.detect_cost_anomalies() == []


def test_prior_window_increase_is_flagged():
    tool = CostExplorerTool(get_settings())
    tool._client = FakeCE("200", "100")
    anomalies = tool.detect_cost_anomalies()
    assert len(anomalies) == 1
    assert anomalies[0].service == "EC2"
    assert anomalies[0].deviation_pct == 100.0
    assert anomalies[0].current_spend_usd == 200.0
    assert anomalies[0].baseline_spend_usd == 100.0


def test_equivalent_windows_match_day_count():
    today = date(2026, 8, 25)
    current_start, current_end, prior_start, prior_end = equivalent_windows(today)
    assert current_start == date(2026, 8, 1)
    assert current_end == today
    assert prior_start == date(2026, 7, 1)
    assert prior_end == date(2026, 7, 25)
    assert (current_end - current_start).days == (prior_end - prior_start).days
