from state import AgentState, ResearchResult, TradeDecision


def research_node(state: AgentState) -> dict:
    """Fetch news and data for each ticker from the web."""
    results = []
    for ticker in state["tickers"]:
        # TODO: use Tavily or SerpAPI to search news for ticker
        # TODO: parse and extract relevant articles
        result: ResearchResult = {
            "ticker": ticker,
            "headline": f"Placeholder headline for {ticker}",
            "sentiment": "neutral",
            "summary": f"Placeholder summary for {ticker}",
        }
        results.append(result)
    return {"research": results}


def portfolio_node(state: AgentState) -> dict:
    """Load current portfolio holdings from storage."""
    # TODO: load from JSON file or DB
    holdings = []
    cash = 10_000.0
    return {"holdings": holdings, "cash": cash}


def analysis_node(state: AgentState) -> dict:
    """Use LLM to analyze research results and produce a summary."""
    research = state["research"]
    # TODO: call LLM with research results and ask for analysis
    summary = f"Analyzed {len(research)} tickers. Placeholder analysis."
    return {"analysis_summary": summary}


def decision_node(state: AgentState) -> dict:
    """Use LLM to decide buy/sell/hold for each ticker."""
    decisions: list[TradeDecision] = []
    for item in state["research"]:
        # TODO: call LLM with analysis_summary + holdings + item to produce a decision
        decision: TradeDecision = {
            "ticker": item["ticker"],
            "action": "hold",
            "quantity": 0.0,
            "reasoning": "Placeholder reasoning",
        }
        decisions.append(decision)
    return {"decisions": decisions}


def memory_node(state: AgentState) -> dict:
    """Persist decisions and reasoning to disk."""
    import json
    from datetime import datetime

    date = state.get("date", datetime.today().strftime("%Y-%m-%d"))
    log_path = f"logs/{date}.json"

    # TODO: mkdir logs if not exists, write decisions to file
    print(f"[memory] Would write decisions to {log_path}")
    return {"log_path": log_path}
