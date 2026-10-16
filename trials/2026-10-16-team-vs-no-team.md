# AI team against no team: Market Review issues 84, 115 and 85

Three features, each built twice from the same issue in Market Review: once with `/team-lead issue N`, once in a
plain session told not to use the team. Measured with `tools/compare-sessions.py` from the session logs; quality
judged blind by a fresh session (X and Y, labels stripped), then by the owner, before the key was opened.
The app deletes a session's logs when the session is deleted, so the numbers below are the only record.

| | #84 bug: heading under the header | #115 make room in site.js | #85 showcases (design-heavy) |
|---|---|---|---|
| Team lane | fast path (5, 7, 8) | fast path (5, 7, 8) | full; design approved 3 times |
| Same start commit | yes, ce5c81b | no: df9cbe2 (no team), 2262462 (team, adds #180) | yes, 7806159 |
| Weighted tokens, team / no team | 4.63 M / 3.85 M | 2.18 M / 1.58 M | 12.39 M / 14.60 M |
| Working time, team / no team | 2h 02m / 1h 14m | 49m / 29m | 4h 32m / 1h 56m |
| Waiting on the owner, team / no team | 0 / 0 | 0 / 1h 18m | 40m / 39m |
| Commands cut at 10 min, team / no team | 3 / 0 | 0 / 0 | 3 / 0 |
| Blind judge picked | team | team | team |
| Owner picked | team (blind) | team (blind) | no team, on product fit (not blind) |
| PR merged | #178 (team) | #184 (team) | #185 (no team), chosen for following the owner's answers |

Notes per feature:
- #84: the team's fix holds the opening address until the fonts are ready; the plain fix relied on the browser's
  timing and missed the cache value. The team's ADR gap was closed by hand before the merge.
- #115: the team freed 1,116 bytes (about 960 of them by removing one indent level), the plain session 142.
  The plain session asked the owner a question and waited; the team asked nothing.
- #85: the issue is labelled `by-claude`, so under the project's rule the team settled the issue's five open
  decisions itself and asked the owner none; the plain session asked the owner and built the owner's answers
  (a slide on every business type page, two new type pages, prices shown). So the two built different features.
  The judge was told not to count a choice against either and judged execution: the team built its choice in
  full with every figure keyed and negative tests; the plain one typed the prices into the text (against the
  issue), dropped the pitch lines, left several claims unkeyed, and changed 6,773 diff lines. The team's run
  also lost time to the PC's "Animation effects" setting being off (12 unrelated browser tests failing) and to
  gate runs; 3h 42m of its time was in shell commands. The team session listed the other branch and PR at its
  start (names only) and compared both PRs at the owner's request after it finished; that last request is left
  out of its numbers.

Owner's reading of #85 (2026-10-16): the team asked far fewer questions, so it built one case on one page; the
plain session's questions led to real cases on every business type page, each from that type's own demo, which
is the better product. The blind judge scored execution of each side's own choices and could not see this, so
"judge picked team" for #85 overstates the team. The cause is the project's `by-claude` rule (no questions),
which overrode the issue's own "Decisions for the owner" list.

Caveats: three features; one judge per feature, of the same model family that built both; #115 started from
different commits; #85 compared different choices.
