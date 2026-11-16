# ADR: the average order in the summary
- **Revision:** 1

## Decision
`data.average_cents(orders)` returns the average order total in cents, rounded half up. `page.render` passes
it to the summary's text. That text stays in `strings.json` under `summary.total`, where every word a visitor
reads lives.

## Allowed Blast Radius (Source)
- `src/orders/data.py` — add `average_cents`
- `src/orders/page.py` — pass the average to the summary
- `src/orders/strings.json` — the new text of `summary.total`

## Allowed Blast Radius (Infra)
- none

## Infra Impact
Infra Impact: no

## Invariants
- INV-1: every word a visitor reads comes from `src/orders/strings.json`. `page.py` holds no sentence.

## Implementation Tasks
- T-1: add `average_cents(orders)` to `src/orders/data.py`.
- T-2: change the text of `summary.total` to the copy file's, and pass `average` to it from `page.py`.
