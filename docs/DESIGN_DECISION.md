# Design Decision: LLM + Heuristics vs Custom ML

## 1. Problem Statement

Synth MVP ingests athlete training and wellness data from two sources — a triathlon training log (individual, 141 days) and a women's rowing erg benchmark dataset (team, 52 athletes × 16 test sessions) — and generates actionable performance insights.

The core engineering question: **how should the system generate insights from the data?**

Two options were evaluated:
- **Option A**: LLM (Gemini) + deterministic heuristics
- **Option B**: Custom machine learning model (supervised or unsupervised)

## 2. Data Characteristics

### Triathlon Training Log
- **Volume**: 141 daily rows, 375 individual activities
- **Time span**: Dec 25, 2025 → May 14, 2026 (~5 months)
- **Populated fields**: Session counts, distances, training minutes, elevation, heart rate (96%), bike power (40%), run pace (44%)
- **Missing fields**: All wellness columns are empty   sleep, HRV, resting HR, body weight (0% fill rate)
- **Labels**: None. No ground truth for "overtraining", "good recovery", or "optimal load."

### Rowing Erg Results
- **Volume**: ~800 individual test results across 52 athletes and 16 sessions
- **Time span**: Sep 8, 2025 → Mar 16, 2026 (~6 months)
- **Formats**: 7 distinct worksheet formats (2k, 6k, 2×6k, 4×1k, 9×2k, 3×12min, 30min)
- **Labels**: None. No ground truth for "improving" beyond split time direction.

### Key constraints
- 141 rows is far below the minimum for meaningful supervised learning
- Empty wellness columns eliminate the most informative features for recovery prediction
- No labeled outcomes exist for any downstream task
- One-week development timeline

## 3. Option A: LLM + Heuristics

### How it works
1. **Heuristics layer** computes deterministic metrics from the data:
   - Training load (TRIMP inspired: minutes × HR intensity factor)
   - Recovery proxy (derived from rest day recency, HR drift, load trends   since wellness data is empty)
   - Sport balance (triathlon discipline distribution)
   - Athlete progression (split improvement over time for rowing)
   - Anomaly flags (training spikes, load changes, pacing inconsistency)

2. **Summary builder** aggregates heuristics into structured prompts containing only computed numbers — never raw data rows.

3. **Gemini** interprets the summaries and returns structured JSON:
   - Insights (factual observations grounded in the data)
   - Risks (potential consequences)
   - Recommendations (actionable steps)

4. **Validation layer** enforces the response schema by requesting `application/json` from Gemini via the official SDK, and falls back to heuristic flags if Gemini is unavailable or errors out (Graceful Degradation).

### Strengths
- **Explainable**: Every insight traces back to a specific metric. "Training load spiked 38%" is verifiable.
- **Testable**: Heuristic functions are pure — known inputs, deterministic outputs, unit-testable.
- **Works at any scale**: Produces valid output with 7 days of data or 141 days.
- **Robust**: The system is useful even without Gemini — heuristic flags still provide value.
- **Extensible**: Adding a new metric (e.g., HRV when data becomes available) means adding one function and updating the prompt template.

### Weaknesses
- LLMs can hallucinate — mitigated by summarising before sending and forcing JSON generation via the SDK.
- Gemini API adds latency (~1–2 seconds) and cost — mitigated by sending summaries, not raw data.
- The prompt template requires maintenance as heuristics evolve.

## 4. Option B: Custom ML Model

### What it would look like
- Supervised regression or classification to predict recovery, injury risk, or performance
- Unsupervised anomaly detection (isolation forest, LOF) to flag unusual patterns
- Time-series forecasting for erg performance prediction

### Why it was rejected

| Factor | Reality |
|---|---|
| **Data volume** | 141 daily rows. Standard ML heuristic: minimum ~500 rows for basic supervised learning, ~1000+ for robust generalisation. Any model trained on 141 rows is memorising the training set. |
| **No labels** | There is no ground truth for "overtraining", "good recovery", or "poor performance." Without labels, supervised learning is impossible. |
| **Missing features** | The most predictive features for recovery — sleep, HRV, resting HR — are 0% populated. Any model trained without these features is missing the most informative signal. |
| **Cross-validation** | With 141 rows, a 5-fold CV has ~28 samples per fold. Statistical significance tests on the difference between model performance across folds would be meaningless. |
| **Explainability** | A model score of 0.73 tells a founder nothing. "Your training load increased 38% while your HR trended upward" is actionable. |
| **Timeline** | Building a defensible ML pipeline — feature engineering, model selection, hyperparameter tuning, validation, documentation — would consume the entire week with an inferior result. |

### Where ML would make sense (future)
- **500+ labeled daily records** with wellness data populated → supervised recovery prediction
- **Perceived exertion ratings** as training labels → effort vs. outcome modelling
- **Multi-season rowing data** with race results → erg-to-race performance prediction
- **Anomaly detection** on 6+ months of data → unsupervised outlier flagging

## 5. Comparison

| Criterion | LLM + Heuristics | Custom ML |
|---|---|---|
| Works with 141 rows | ✅ Yes | ❌ Memorises noise |
| Works without labels | ✅ Yes | ❌ Supervised impossible |
| Works without wellness data | ✅ Recovery proxy from training signals | ❌ Missing most informative features |
| Explainable to a founder | ✅ Natural language grounded in numbers | ❌ Opaque scores |
| Unit-testable | ✅ Pure functions | ⚠️ Only via integration tests |
| Buildable in one week | ✅ 2–3 days | ❌ Entire week, still unreliable |
| Extensible | ✅ Add function + update prompt | ⚠️ Retrain model |
| Degrades gracefully | ✅ Heuristic flags without Claude | ❌ No model = no output |

## 6. Chosen Approach

**LLM + Heuristics**, for the reasons above.

The system was intentionally designed around `daily_summary` and `activities_raw` because aggregate training and recovery metrics were sufficient for MVP insight generation. Split level sheets (swim, bike, run splits) were identified as a future enhancement for interval level analysis   including them would have dramatically increased parsing complexity, join complexity, and testing surface without materially improving the insight quality for this submission.

## 7. Tradeoffs Acknowledged

### LLM hallucination risk
**Mitigation**: The LLM never sees raw data. It receives pre computed summaries with specific numbers. The response is validated by forcing `application/json` at the SDK level. If validation or the API call fails, the system catches the error and returns heuristic flags as degraded mode insights.

### Recovery proxy vs real wellness data
**Mitigation**: The recovery proxy uses rest day recency (binary, reliable), HR drift (derived, moderately reliable), and load trend (computed, reliable). It's explicitly documented as a proxy, not a measurement. The schema is ready for real wellness data when it becomes available   adding sleep and HRV would improve the recovery score without changing the architecture.

### Prompt injection from Excel data
**Mitigation**: Only computed numeric summaries enter the Gemini prompt. Raw string fields from the spreadsheet (athlete names, notes) are strictly sanitized via regex before they ever hit the pipeline, throwing a 422 exception if malicious tags like `<script>` are detected. Alert flags are internally generated strings.

## 8. Future Evolution

### Phase 2 (with more data)
- Populate wellness columns (sleep, HRV, resting HR) → upgrade recovery proxy to true recovery score
- Add perceived exertion from athletes → first labeled outcome for potential ML

### Phase 3 (with 500+ labeled records)
- Explore anomaly detection (isolation forest) alongside heuristics
- Time series forecasting for rowing erg performance
- Ensemble approach: heuristics provide the base, ML adds statistical power

### Phase 4 (production)
- Split level analysis for interval training optimisation
- Multi athlete support with per athlete baselines
- Real time Strava webhook integration (replace Excel ingestion)
- Background task queue for Gemini calls

---

*This document was updated during development to reflect the migration from Claude to Gemini due to API access limitations, proving the resilience of the Graceful Degradation architecture.*
