# AGENTS.md

Guidelines for AI coding agents working in this repository.

This repository contains a Streamlit-based market analysis dashboard:
**Pre-Market War Room**

Agents must follow these rules when reviewing or modifying the codebase.

------------------------------------------------------------------------

# 1. Project Overview

The application is a **single-file Streamlit app** designed for daily
market analysis.

Core functions include:

-   Market regime detection
-   Macro environment monitoring
-   Sector rotation analysis
-   Watchlist radar
-   AI-assisted pre-market narrative

The system emphasizes:

-   robustness
-   predictable behavior
-   minimal runtime failures

Agents must prioritize **stability over feature expansion**.

------------------------------------------------------------------------

# 2. Architecture Principles

Agents must follow these engineering principles:

1.  Prefer **minimal patching** over refactoring
2.  Preserve the existing architecture
3.  Avoid moving large code blocks
4.  Avoid renaming functions unless required by spec
5.  Do not introduce unnecessary abstractions

This project intentionally uses a **single-file architecture**.

Do not split the application into multiple modules unless explicitly
instructed.

------------------------------------------------------------------------

# 3. Specification Priority

When modifying the code, follow this priority order:

1️⃣ `spec_patch_v*.md`\
2️⃣ existing working Python code\
3️⃣ base specification documents (`spec_premarket_warroom_v*.md`)

Interpretation rules:

-   Patch specifications override base specifications
-   Existing working behavior should be preserved when not explicitly
    modified
-   If ambiguity exists, prefer the **minimal-change interpretation**

------------------------------------------------------------------------

# 4. Protected Core Components

The following components are **architecture guard boundaries**.

Agents must NOT modify their core logic.

## 4.1 Market Regime Engine

Protected function:

`determine_market_regime()`

Rules:

-   Do not modify the regime classification logic
-   Do not introduce new regime factors
-   Do not add DXY / Real Yield / liquidity engine logic
-   Do not change priority ordering

These changes are reserved for **future major versions (V2.0+)**.

------------------------------------------------------------------------

## 4.2 Data Fetch Isolation

Function:

`_fetch_all_data()`

Must preserve:

-   isolated `try/except` blocks for each data source
-   failure of one API must NOT break the entire fetch cycle
-   partial data must still allow UI rendering

------------------------------------------------------------------------

## 4.3 Cache Guard System

Functions:

`_has_valid_cache_guard_data()`

Constants:

`CACHE_GUARD_SYMBOLS`

Rules:

-   cache updates must only occur when guard symbols are valid
-   do not remove or weaken this validation

------------------------------------------------------------------------

## 4.4 Session State Safety

Session state must only store:

-   processed data
-   lightweight dictionaries
-   rendered-ready objects

Agents must NOT store raw large DataFrames directly in session state.

------------------------------------------------------------------------

# 5. External API Safety

External services include:

-   yfinance
-   FRED
-   OpenAI
-   Gemini

All external calls must follow:

    try:
        ...
    except Exception:
        fallback

Rules:

-   API failures must not crash the app
-   missing values must render "N/A"
-   UI must remain usable even when APIs fail

------------------------------------------------------------------------

# 6. UI Stability Rules

The UI must remain stable even under partial data conditions.

Rules:

-   no uncaught exceptions in Streamlit rendering
-   metrics must tolerate missing values
-   tables must render even if some columns are unavailable

Never allow a failed API call to produce a blank page.

------------------------------------------------------------------------

# 7. AI Integration Principles

The AI layer is **interpretive**, not authoritative.

Rules:

-   AI must NOT determine market regime
-   AI must NOT override rule-engine outputs
-   AI output is explanatory only

The rule engine remains the **source of truth**.

------------------------------------------------------------------------

# 8. Performance Considerations

Agents should avoid changes that significantly increase runtime.

Avoid:

-   unnecessary API calls
-   repeated data downloads
-   redundant computations

Prefer reusing already-fetched data.

Example:

If `SMH` already exists in `price_data`, do NOT fetch it again.

------------------------------------------------------------------------

# 9. Safe Data Handling

When computing indicators:

-   always handle `None`
-   always handle `NaN`
-   ensure safe fallback values

Example pattern:

    value = round(x, 2) if pd.notna(x) else "N/A"

Never assume external data is valid.

------------------------------------------------------------------------

# 10. Versioning Rules

New versions should follow the naming pattern:

`premarket_warroom_vX_Y.py`

Examples:

-   premarket_warroom_v1_2.py
-   premarket_warroom_v1_2\_1.py
-   premarket_warroom_v1_3.py

Agents should not overwrite historical versions unless explicitly
instructed.

------------------------------------------------------------------------

# 11. Change Philosophy

This project favors:

-   incremental upgrades
-   safe patches
-   predictable behavior

Agents must avoid:

-   speculative improvements
-   architecture redesign
-   large-scale refactors

If a requested change appears to require major redesign, agents should
**flag the issue rather than implement it silently**.

------------------------------------------------------------------------

# 12. When in Doubt

If a specification is ambiguous:

1.  prefer the minimal-change solution
2.  preserve current behavior
3.  avoid introducing new dependencies
4.  avoid modifying protected components

Stability is more important than elegance.
