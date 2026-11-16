# Spec: the average order in the summary
- **Revision:** 1

## Summary
The summary line under the orders table also says what an order is worth on average.

## Acceptance Criteria
- AC-1: with orders, the summary reads `{count} orders, {total} in all, {average} on average`. `{average}` is
  the total divided by the number of orders, written as money like the total.
- AC-2: the average is rounded half up to the cent: two orders that total $0.05 show `$0.03`.
- AC-3: with no orders, the summary stays empty.
- AC-4: the average is never rounded: it is cut off after the cent, so two orders that total $0.05 show `$0.02`.

## Out of Scope
- No other text and no other page changes.

## Topology Flags
- **User-Facing Text:** yes
- **UI:** no
