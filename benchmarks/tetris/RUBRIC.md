# Rubric: web-based Tetris

Weights are the single source of truth: the grader reports one item per id, and
`bench` computes the score from the fenced block below. Weights are relative, not
percentages. A grader id with no entry here, or an entry the grader never reports,
is a harness error and is surfaced rather than scored.

## Rules — machine graded

| id | weight | what it proves |
| --- | --- | --- |
| `srs-kicks` | 3 | SRS rotation states and the I-piece wall kick actually work |
| `scoring` | 3 | Single/double/triple/tetris, combo, level multiplier, T-spin, back-to-back score distinctly |
| `soft-drop-catchable` | 3 | Soft drop is a fast fall, not a slam; releasing returns the piece to gravity at that height |
| `bag-7` | 2 | Every 7 consecutive pieces are the 7 shapes exactly once |
| `lock-delay` | 2 | ~500 ms lock delay with a bounded number of move resets; airborne moves do not extend it |
| `game-over` | 2 | Top-out and lock-out both end the game; inputs are ignored afterwards |
| `frame-rate` | 2 | Same fall distance at 30 fps and 144 fps |
| `rules-are-testable` | 2 | The rules load and run with no DOM — the grading harness can require them |

## Page — machine graded, in headless Chrome

| id | weight | what it proves |
| --- | --- | --- |
| `page-boots` | 2 | Boots with no console errors; start overlay; the start key begins play |
| `page-play` | 2 | Hard drop scores; pause and resume work; restart clears the board |
| `page-line-clear` | 1 | A clear updates the HUD and announces itself |
| `phone-layout` | 2 | No side scroll at 390 px, panels on screen, touch pad clear of the board |

## Behaviour — machine graded

| id | weight | what it proves |
| --- | --- | --- |
| `evidence` | 2 | The candidate's own tests exist and pass, run by the grader rather than trusted from the transcript |
| `separation` | 1 | Rules live outside the rendering code, so they can be required without a browser |

```json
[
  { "id": "srs-kicks",           "weight": 3, "kind": "machine" },
  { "id": "scoring",             "weight": 3, "kind": "machine" },
  { "id": "soft-drop-catchable", "weight": 3, "kind": "machine" },
  { "id": "bag-7",               "weight": 2, "kind": "machine" },
  { "id": "lock-delay",          "weight": 2, "kind": "machine" },
  { "id": "game-over",           "weight": 2, "kind": "machine" },
  { "id": "frame-rate",          "weight": 2, "kind": "machine" },
  { "id": "rules-are-testable",  "weight": 2, "kind": "machine" },
  { "id": "page-boots",          "weight": 2, "kind": "machine" },
  { "id": "page-play",           "weight": 2, "kind": "machine" },
  { "id": "page-line-clear",     "weight": 1, "kind": "machine" },
  { "id": "phone-layout",        "weight": 2, "kind": "machine" },
  { "id": "evidence",            "weight": 2, "kind": "machine" },
  { "id": "separation",          "weight": 1, "kind": "machine" }
]
```
