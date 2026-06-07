from datetime import datetime
from graph import graph


def run(tickers: list[str], date: str | None = None):
    initial_state = {
        "tickers": tickers,
        "date": date or datetime.today().strftime("%Y-%m-%d"),
        "research": [],
        "holdings": [],
        "cash": 0.0,
        "analysis_summary": "",
        "decisions": [],
        "log_path": "",
    }

    result = graph.invoke(initial_state)

    print("\n=== Decisions ===")
    for decision in result["decisions"]:
        print(f"  {decision['ticker']}: {decision['action']} {decision['quantity']} — {decision['reasoning']}")

    print(f"\nLog saved to: {result['log_path']}")
    return result


if __name__ == "__main__":
    run(tickers=["AAPL", "NVDA", "MSFT"])
