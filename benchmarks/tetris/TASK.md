# Task: web-based Tetris

**Artifact:** a self-contained web app in the run workspace
**Graded by:** `grader/grade.js` — see `RUBRIC.md` for the weighted checklist
**Runs:** `bench run tetris --model <provider/id>`

This is a prompt template. `{{workspace}}` is substituted at launch with the
absolute path of the run's workspace, so the same text produces a comparable run
on any machine. The prompt itself is never edited between runs — if it must
change, the task version in `meta.json` changes with it, and old runs stay
comparable to each other but not to new ones.

## Why this task

It is a good probe of agentic coding because it cannot be satisfied by prose:

- The rules are **specified but fiddly** — SRS wall kicks, 7-bag randomisation and
  lock-delay resets are all things a model will get subtly wrong unless it tests
  them. Correct-looking code that fails the kick table is the common failure.
- It demands **separation of concerns**. "Keep the rules testable without a DOM"
  is a design instruction, and a model that ignores it produces code that cannot
  be graded and cannot be maintained.
- It has a **subjective requirement** ("feels good to play") that resists being
  pattern-matched, and a **specific correction** in turn four that tests whether a
  model can revise a decision rather than defend it.
- It ends in **evidence**. "Prove it works before you say you're done" separates
  models that run their tests from models that describe running their tests.

## Turn 1 — the canonical prompt

```text
Build me a web-based Tetris game in {{workspace}}. Plain HTML/CSS/JS, canvas
rendering, no build step and no dependencies — it should run by opening
index.html.

It has to actually feel good to play, so use modern mechanics: 10x20 well,
SRS rotation with proper wall kicks, 7-bag randomiser, hold, ghost piece, a
next queue, lock delay, and guideline-style gravity and scoring (combos,
T-spins and back-to-back welcome). Keyboard controls, and it should not fall
apart on a phone screen.

Keep the game rules out of the DOM code so the rules can be unit-tested
headlessly, and prove the thing works before you tell me you're done: write the
tests, run them, and drive the real page in a browser to confirm it boots,
scores, pauses, tops out and lays out correctly at phone width. Report the
evidence, not just the intent — and if a test fails, say so and fix it.

One specific feel requirement, learned the hard way by other runs: soft drop
must be a fast fall, not a second hard drop. Holding the soft-drop key should
drop the piece at a higher speed than gravity — but slowly enough that a player
with quick reactions can release the key mid-fall and then steer and rotate at
that altitude, after which the piece goes back to the level's normal gravity
speed. The piece must not slam to the floor and lock the moment the key goes
down, and time spent falling under soft drop should score as it normally does.

Tell me where the tuning knobs live when you're finished.
```

## Turns 2–4 — replay mode

`meta.json.turns` carries all four turns. `bench run --turns replay` sends them in
order against one session, which scores three things a single prompt cannot:

2. `` `{{workspace}}` please `` — sent as the answer to "what kind of Tetris do
   you want, and who is it for?". An implicit *"stop asking, start building, at
   this path"*. A model that keeps interrogating has failed this turn.
3. `Are we done? Seem to have stopped` — the run has stalled mid-task. Scores
   whether the model re-orients on what already exists and finishes, or starts
   over.
4. A correction to the soft-drop feel, quoted in full in `meta.json`. Scores
   whether the model revises a design decision it had already made and shipped,
   without regressing the rest.

Turn four is the interesting one. It is the only turn that can only be answered
by a model that already committed to a wrong-but-defensible choice.
