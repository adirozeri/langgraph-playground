# Fundamental Analysis in the AI Era
### Valuing a company without touching a spreadsheet

A practical guide distilled from a two-part video series on doing fundamental analysis with AI tools. It covers the full method: what the key performance indicators mean, how to ask an AI the right questions, how to build four decision dashboards, and how to turn all of it into an investment view, along with the limits you must respect.

> **Not financial advice.** This summarizes an educational framework. It is opinion and method, not a recommendation to buy or sell any security. Every figure an AI produces must be grounded in real financial data, or it will be invented.

---

## Contents

1. [Why the method changed](#1-why-the-method-changed)
2. [The pipeline at a glance](#2-the-pipeline-at-a-glance)
3. [Phase 0: Know the business first](#3-phase-0-know-the-business-first)
4. [The four measurable pillars](#4-the-four-measurable-pillars)
5. [The smart way to prompt](#5-the-smart-way-to-prompt)
6. [The four dashboards](#6-the-four-dashboards)
7. [From data to a decision](#7-from-data-to-a-decision)
8. [The limits you must respect](#8-the-limits-you-must-respect)
9. [Quick-start checklist](#9-quick-start-checklist)

---

## 1. Why the method changed

The starting point is a remark by Ken Griffin, CEO of Citadel, the world's largest market maker. He observed that work normally done by people with master's degrees and PhDs in finance, over the course of weeks or months, is now being done by AI agents over the course of hours and days. The people he is describing are not the average analyst; they sit at the very top of the field. The conclusion the series draws is simple: if AI can do that level of work, there is no reason for an ordinary investor not to use it.

**The central insight.** The old skill of fundamental analysis did not die. It split in two. The **mechanical part** (reading hundreds of pages of annual reports, computing ratios by hand, filling in Excel, comparing quarter against quarter going back years) is now obsolete because AI does it faster and better. The **conceptual part** (knowing which metrics matter, what to ask, and how to connect everything into a judgment) became more important than ever, because only that knowledge lets you write a prompt worth trusting.

> **The one rule that makes this work**
>
> **Connect the AI to real financial data, or paste real data in yourself.** If you do not, the model will produce numbers that look authoritative and are entirely made up. The tool recommended in the series for this is Perplexity Finance (free or very low cost), with Koyfin named as the paid alternative the presenter personally uses at roughly $600 a year.

---

## 2. The pipeline at a glance

The whole method is six phases. The rest of the document expands each one.

| Phase | What you do | Who does it |
|-------|-------------|-------------|
| 0  Know the business | Explore the product, read about the company, watch the CEO speak | You, no AI |
| 1  Set up the tool | Use a data-connected AI platform so numbers are real | You |
| 2  Pull the KPIs | Gather the ~25 metrics across four pillars | AI + real data |
| 3  Prompt precisely | Ask specific, time-bound, comparative questions | You design, AI runs |
| 4  Build dashboards | Compress everything into four snapshots | AI |
| 5  Decide | Score, value, project, cross-check, conclude | You, AI assists |

---

## 3. Phase 0: Know the business first

Before a single number, get to know the company as a product and a story. Go to the company website and click through it. Look at what it actually sells. Read the "about" section. Watch the CEO speak on YouTube. The goal is to understand and **feel** what the business does and how it makes money.

**Why no AI here.** This step is about experiencing the company directly. An AI can summarize who the company is, but it cannot form your intuition for you. Skip this and every later number floats without context.

---

## 4. The four measurable pillars

Phase 0 is qualitative. The measurable work is organized into four pillars holding roughly 25 KPIs, plus a set of forward-looking signals. Below is each pillar with what every metric tells you.

### 4.1 Profitability: is the company actually making money?

| Metric | What it tells you |
|--------|-------------------|
| Revenue growth rate | How fast sales grow. Watch the rate, not the level. 100→110→120 is decelerating; 100→110→130 is accelerating. |
| Gross margin | Revenue minus the direct cost to produce it. Shows pricing power. |
| Operating margin | Profit after operating expenses. Measures efficiency. You do not want a "fat" business. |
| Net margin | What is left on the bottom line after everything. |
| EPS | Earnings per share. Buybacks shrink share count and lift EPS. |
| EBITDA | Earnings before interest, taxes, depreciation, amortization. A pre-adjustment profit figure; treat the adjustments with care. |

### 4.2 Valuation: what is it worth and what are you paying?

| Metric | What it tells you |
|--------|-------------------|
| P/E | Price divided by earnings. A common yardstick to compare across companies. |
| Forward P/E | Uses analyst-expected earnings. This is the one to favor, because you are valuing the future, not the past. |
| P/S | Market cap divided by revenue. Useful for fast growers. |
| EV/EBITDA | Enterprise value over EBITDA. Capital-structure-neutral valuation. |
| PEG | P/E divided by earnings growth rate. Built for growth companies. |
| P/B | Price to book. Mainly for tech and asset-heavy firms. |

### 4.3 Cash flow: how much real cash is generated?

| Metric | What it tells you |
|--------|-------------------|
| Operating cash flow | Cash generated by the actual business. Hard to manipulate. |
| Free cash flow | Operating cash flow minus capital expenditure. The cash genuinely left over. |
| Free cash flow margin | Free cash flow as a percentage of revenue. |
| Free cash flow yield | Free cash flow divided by market cap. The return the cash represents. |

### 4.4 Financial strength: can it survive and compound?

| Metric | What it tells you |
|--------|-------------------|
| Debt to equity | How much debt sits against shareholder equity. |
| Net cash vs net debt | Whether the company has more cash than debt, or the reverse. |
| Current ratio | Assets over liabilities. Short-term solvency. |
| ROE | Return on equity. Net income over shareholder equity. |
| ROIC | Return on invested capital. How well management turns capital into profit. |

### 4.5 Forward-looking signals (check every earnings report)

- **Guidance.** What management says is coming.
- **Analyst estimates.** What the people who already modeled the future expect.
- **Earnings revisions.** Are estimates being raised or lowered? Direction matters.
- **Buybacks.** Is the company reducing share count?
- **Insider transactions.** Are insiders buying or selling their own stock? If everyone inside is selling, the expectations story has a hole.

---

## 5. The smart way to prompt

This is the heart of the method. The mistake is asking the AI a lazy question like *"is this a good stock?"* You get vague mush back, then blame the tool. The fix is to ask precise, time-bound, comparative questions.

The example pattern from the series:

```
What is TICKER free cash flow margin trend over 8 quarters
versus the sector median?
```

**Every good prompt carries three ingredients:**

1. **A specific KPI** (free cash flow margin, not "performance").
2. **A time window** (8 quarters; or 5 to 10 years for valuation history).
3. **A comparison** (against the sector median, or named peers).

> **The single biggest advantage of using AI**
>
> One prompt can run a company against several peers at once. You can compare NVIDIA to AMD, Broadcom, and Intel in the same query, instead of researching each one separately. No company should ever be judged in isolation.

### A reusable template

```
For TICKER, report [KPI] over the last [N quarters/years].
Show the trend, compare against [peers or sector median],
and flag whether it is improving or deteriorating.
Use connected financial data only — no estimates.
```

**If a prompt breaks.** Paste it into a general chatbot and ask it to fix the prompt for you. Swap the word TICKER for the company's symbol each time.

---

## 6. The four dashboards

A full deep dive can run to about 37 pages, one metric at a time, which is available when you want everything. For a fast read, the series collapses it into four snapshots. Build one prompt per dashboard. Together they give a complete picture at a glance.

| Dashboard | Question it answers | What it contains |
|-----------|---------------------|------------------|
| Income (Foundation) | Is it making money? | Revenue, the profitability stack, free cash flow, and whether the pace is satisfactory. |
| Momentum (Engine) | Is it speeding up or slowing down? | Yearly EPS, revenue, free cash flow, sales vs guidance, P/E history vs forward. Rate of change is the focus. |
| Valuation (Price) | Is it cheap or expensive vs itself? | P/E, P/S, EV/EBITDA, EV/gross profit over 5 to 10 years, flagged cheaper or richer than its own history. |
| Capital (Allocation) | Does management use money well? | ROIC, revenue per employee trend, buybacks, and the analyst view on the current price. |

> **On valuation history**
>
> Seeing that a company is cheaper or more expensive than its own 5-to-10-year range tells you about its pricing, not whether to buy. It does not say the stock is a good deal or a bad one. It only lets you understand where today sits against the past.

---

## 7. From data to a decision

This is the step the videos leave loosest, and it is where the analysis becomes meaningful instead of merely informative. Work through it in order.

1. **Score each pillar relative to peers, not in a vacuum.** You want a company beating its sector on profitability, cash flow, and capital efficiency. One losing pillar is a flag, not an automatic veto.
2. **Place valuation against its own history.** Judge whether you are paying up or getting a discount on a 5-to-10-year view, while remembering this alone is not a buy or sell signal.
3. **Build a base case and a bull case for three years.** Ask the AI to construct projections from the analyst estimates it already has, then write down the assumptions explicitly so you can challenge them.
4. **Cross-check the soft signals.** Are insiders buying or selling? Are analysts revising up or down? Is there a buyback? Flag any conflict, for example rising estimates alongside heavy insider selling.
5. **Conclude.** A healthy business, improving versus peers, at a non-stretched valuation, with insiders and revisions pointing the same way, is the setup that argues for investing. The opposite combination argues against.

### 7.1 The three numbers to weight most

If you reduce everything to three checks, the series points to these:

- **Free cash flow.** Is it a real cash machine, or a treadmill running hard and producing little?
- **Revenue growth rate.** And critically, is it accelerating or decelerating?
- **ROIC versus cost of capital.** If ROIC is below the cost of capital, the company destroys value even while it grows.

---

## 8. The limits you must respect

The honesty of the method lives here. None of this is skippable when you act on the analysis.

> **Three hard limits**
>
> **1. Fundamentals give quality, not timing.** They tell you whether a business is healthy, not when to buy. A great business can fall for a year.
>
> **2. The AI absorbs everything, exactly like Excel did.** Feed it bad assumptions and it will build a beautiful, confident model on top of garbage. Output quality equals your assumption quality.
>
> **3. A projection is not a guaranteed target.** A three-year value estimate is how the market would value the company on today's data. War, inflation, new technology, or a change at the company can break the whole model.

---

## 9. Quick-start checklist

Run this loop for any company you want to analyze.

1. Open the company website and watch the CEO speak. Form a first impression.
2. Open a data-connected AI tool (Perplexity Finance, or paste real data yourself).
3. Pull the four pillars: profitability, valuation, cash flow, financial strength.
4. Use precise prompts: KPI + time window + peer comparison, every time.
5. Generate the four dashboards: Income, Momentum, Valuation, Capital.
6. Check the soft signals: guidance, revisions, buybacks, insider trades.
7. Score pillars vs peers, place valuation vs history, build base and bull cases.
8. Conclude invest / hold / avoid, and write down the assumptions behind it.
9. Re-run at every earnings report; the picture changes.

> **The bottom line.** Learn the KPIs, let AI do the mechanics, ask sharp comparative questions, and judge the business against its peers and its own history. The output is a grounded view of quality and relative value, plus a reasoned lean. It is not certainty, and it is not a date. Practice it repeatedly and do not be afraid to refine your prompts.
