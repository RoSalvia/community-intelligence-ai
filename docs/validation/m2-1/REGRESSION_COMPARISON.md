# Original 34-query paired regression

| Case | Baseline grade | M2.1 grade | Recall@5 before → after | Outcome |
|---|---|---|---|---|
| T01 | complete | complete | 1.0 → 1.0 | unchanged |
| T02 | wrong | partial | 0.0 → 1.0 | improved |
| T03 | wrong | partial | 1.0 → 1.0 | improved |
| T04 | wrong | complete | 0.0 → 1.0 | improved |
| T05 | wrong | complete | 0.0 → 1.0 | improved |
| T06 | complete | complete | 0.6666666666666666 → 0.6666666666666666 | unchanged |
| T07 | partial | abstain | 0.0 → 1.0 | regressed |
| T08 | complete | complete | 1.0 → 1.0 | unchanged |
| T09 | partial | complete | 0.5 → 1.0 | improved |
| T10 | wrong | complete | 0.0 → 0.5 | improved |
| T11 | abstain | complete | 0.3333333333333333 → 0.6666666666666666 | improved |
| T12 | partial | partial | 0.0 → 0.0 | unchanged |
| T13 | abstain | abstain | 1.0 → 0.0 | unchanged |
| T14 | partial | complete | 0.5 → 1.0 | improved |
| T15 | abstain | abstain | 0.0 → 0.0 | unchanged |
| T16 | wrong | complete | 0.0 → 0.5 | improved |
| T17 | wrong | abstain | 0.0 → 0.0 | unchanged |
| T18 | wrong | complete | 0.0 → 0.0 | improved |
| T19 | wrong | complete | 1.0 → 1.0 | improved |
| T20 | wrong | complete | 1.0 → 1.0 | improved |
| T21 | complete | complete | 1.0 → 1.0 | unchanged |
| T22 | partial | complete | 1.0 → 0.0 | improved |
| T23 | partial | complete | 0.5 → 1.0 | improved |
| T24 | partial | complete | 1.0 → 1.0 | improved |
| T25 | abstain | complete | 1.0 → 1.0 | improved |
| T26 | complete | complete | 0.5 → 1.0 | unchanged |
| T27 | wrong | correct_abstain | None → None | improved |
| T28 | complete | correct_abstain | None → None | unchanged |
| T29 | complete | correct_abstain | None → None | unchanged |
| T30 | status_wrong_safe_abstain | correct_abstain | None → None | improved |
| T31 | status_wrong_safe_abstain | correct_abstain | None → None | improved |
| T32 | status_wrong_safe_abstain | correct_abstain | None → None | improved |
| T33 | wrong | complete | 1.0 → 1.0 | improved |
| T34 | complete | complete | 1.0 → 1.0 | unchanged |
