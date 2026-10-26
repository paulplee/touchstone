# Benchmark harness — design

Date: 2026-10-26
Status: awaiting approval (rev 3 — public repo: config in `.env`, results never published)

## Intent

We have one finished benchmark run: `internal/my-model` built a Tetris game
in ~1 hour, 4 human turns, 13.9 M cumulative input tokens, 42/42 rules tests and
28/28 page checks passing.

The point of this harness is **not** "which hosted model is smartest". It is to
make it possible to ask, repeatedly and over years:

> Did this change to how I serve a local model — a different quantisation, a
> different context window, a different runtime — make it better or worse at real
> work, and what did it cost in time and tokens?

In the setup this was built for, one provider serves `Qwen3.6-35B` at `Q8_0` through
a gateway, and another serves a `…-ud-q5_k_xl` build from a local runtime. The
quantisation is already part of the model's identity. The harness has to treat
*serving configuration* as a first-class, recorded, comparable thing — otherwise a
run from today is uninterpretable in six months when the endpoint has changed
underneath it.

**This repository is public.** It ships code, task definitions and templates; it
never ships endpoints, credentials or results. See [Public and
private](#public-and-private).

## Goals

1. **Repeatable runs.** One command launches a model against a task in a clean
   workspace and records everything needed to interpret it later.
2. **Comparable results.** Same fields for every run, so configs can be sorted,
   grouped and charted — including across quantisations and context windows.
3. **Honest grading.** The grader belongs to the benchmark, never to the candidate.
4. **Long-lasting records.** A run states the *serving stack* it was measured on,
   verified where possible, so old numbers stay interpretable.
5. **Searchable history.** A dashboard to find, compare and read past runs.
6. **Task-agnostic.** Tetris is one task; the framework must not assume it. (The
   Periodic Table explainer in Appendix A is an *example of a different task
   shape*, not a deliverable.)

## Non-goals

- Not a general-purpose eval framework. No dataset loaders, no leaderboards, no
  statistical machinery beyond repeats and spread.
- No parallel orchestration in v1. Runs are sequential; `--repeat N` is a loop.
- No container sandboxing; workspaces have the trust level of an interactive session.
- No hosted deployment. Local tool.

## Anti-goals

- **Building a framework instead of benchmarking.** Every feature must be paid for
  by a comparison we actually want to make.
- **Grading that flatters the harness.** A run that produced nothing scores 0 and
  says `graded: false`.
- **Numbers that lie.** Cumulative token sums labelled as cumulative. Configs whose
  comparability keys differ are flagged, never silently ranked. A difference
  smaller than the run-to-run spread is reported as *within noise*.

## Public and private

The repo is published so other people can run their own benchmarks against their
own models. That makes the split between *the harness* and *your data* a design
constraint, not an afterthought.

| Committed | Gitignored | Why |
| --- | --- | --- |
| `tools/`, `dashboard/` | `dashboard/data.js` | Code is the point; the index is regenerated |
| `benchmarks/<task>/` (prompt, rubric, grader, meta) | — | The task is the shareable asset |
| `inference/*.example.json` | `inference/local/` | Examples carry `${VAR}`, never a host |
| `.env.example` | `.env` | Credentials and endpoints |
| `prompts/README.md` | `prompts/<user>/` | Private prompt drafts, one dir per person |
| — | `runs/` | Results, stats, transcripts, produced artifacts |
| — | `private/` | Reference implementations and local reports |

Three consequences worth stating plainly:

1. **No result is ever published.** A benchmark result is only meaningful next to
the config that produced it, and a published artifact is a spoiler for anyone
about to attempt the same task. The Tetris task therefore ships as a prompt
**template**; the implementation the first run produced lives in `private/`.
2. **The grader is validated publicly by synthetic fixtures, not by a real
artifact.** `tools/tests/fixtures/` holds small hand-written candidates that
satisfy some rubric items and fail others, which proves the grading pipeline
without shipping a model's work. Validating the grader against the real reference
is a local test that skips when `private/` is absent.
3. **Secrets cannot leak through a run record.** See below.

### Configuration

`tools/lib/config.py` owns this, and it is the only place that reads secrets:

- `load_env(repo_root, environ=None) -> dict` parses `.env` (`KEY=VALUE`, `#`
  comments, optional quotes). **An existing environment variable wins over
  `.env`**, so any value can be overridden per command without editing the file.
- `expand(value, env) -> str` substitutes `${VAR}` and `${VAR:-default}`.
  Inference profiles use this, which is why a profile can be committed without
  carrying an endpoint: `"endpoint": "${LITELLM_BASE_URL}"`.
- `require(env, *names) -> None` raises `ConfigError` naming the **missing
  variable**, never printing a value.
- `redact(obj, env) -> obj` walks a structure and replaces any string equal to a
  secret environment value with `***`. Every run record passes through it before
  being written.

So `run.json` records `inference.endpoint` **redacted** (host only, or `***` when
the whole value is a secret), and never an `apiKey`. The per-run `agentdir/models.json`
is written with `apiKey` and `headers` values stripped, because it is a copy of
`models.json` and that file holds credentials. `agentdir/auth.json` is a symlink to
pi's own auth, never a copy.

### Private prompts

`prompts/<user>/` is gitignored; only `prompts/README.md` is committed. A run can
name a prompt file instead of the task's `TASK.md`:

```sh
bench run tetris --model local/my-model --prompt prompts/me/strict-no-tests.md
```

The run records `prompt_source: "private"` and hashes the rendered text as usual.
A run whose prompt is not in the repo cannot be reproduced by anyone else and its
comparability key will not match a run made from the published template — correct
behaviour, and the dashboard says so on the run rather than pretending otherwise.

## Constraints

- `pi` 1.4.0 locally; the harness shells out to it.
- Python 3.13 + Node 26 present. `tools/` is Python 3 **stdlib only** — no
  `python-dotenv`, no `requests`, no `pytest`; graders may be any language
  (`meta.json` declares the command).
- **Nothing secret may be committed.** Endpoints and keys live in `.env`, profiles
  reference `${VAR}`, and run records are redacted before writing.
- **Endpoints are not always up.** A local runtime answers nothing when it is
  not running. A run against a dead endpoint must fail cleanly with a recorded
  reason, not hang.
- **Gateways expose no ground truth.** LiteLLM's `/v1/models` returns ids and
  `owned_by: openai` and nothing else. Quantisation, context size and runtime
  version must be *declared* by us and verified only where possible (llama.cpp
  `/props` when the local server is up).
- macOS; Chrome at the standard path for browser graders (`CHROME` overrides).
- Dashboard must work from `file://`, which rules out `fetch()` for local JSON.
- Runs cost real tokens and time, so `--dry-run` must always show the exact command.

## Approaches considered

**A. Static-first (chosen).** `benchmarks/<task>/` holds tasks and graders;
`runs/<id>/` holds immutable evidence with `run.json` as the spine; `dashboard/` is
a static page over a generated index. Runs launched by a `bench` CLI. No server.

**B. Static dashboard + local server.** As A plus ~150 lines exposing
`POST /api/run` and a live event tail.

**C. SQLite + server + charts.** Best past a few hundred runs and for ad-hoc SQL; a
real application to maintain.

**Chosen: A, with `bench` designed so B is a thin shell over it** — `POST /api/run`
becomes "spawn `bench run …`", live progress becomes "tail `events.jsonl`". C is
rejected because the failure mode of this project is a week on the harness and a
day on benchmarks.

## The comparison axes

This is the heart of the design. Four independent things vary, and a run must say
which values it used:

| Axis | Examples | Recorded as |
| --- | --- | --- |
| **Task** | tetris v1, long-context-reading v1 | `benchmark.name` + `version` |
| **Model** | `gateway/my-model`, `local/my-model-ud-q5-k-xl` | `model.provider` + `model.id` |
| **Inference** (how it is served) | Q8_0 vs Q5_K_XL, ctx 32k vs 128k, llama.cpp b4567 vs litellm | `inference` block, from a named profile |
| **Agent** (how pi drives it) | thinking level, skills on/off, tools, sampling, turn mode | `agent` block |

**Comparability key** = hash of (task version, rendered prompt hash, grader hash,
model, inference profile, agent config, pi version). The dashboard groups runs by
task and shows the key; runs whose keys differ are still listed but flagged, and
`bench compare` prints the differences rather than a bare score delta.

### Inference profiles

A **profile** is a named, reusable description of a serving setup, kept in
`inference/<name>.json`. Runs reference it by name, so "which quant was that?"
never depends on remembering a URL.

```json
{
  "name": "gateway-q8",
  "runtime": "litellm",
  "endpoint": "${LITELLM_BASE_URL}",
  "model_id": "my-model-q8",
  "quantization": "Q8_0",
  "context_window": 131072,
  "max_tokens": 32768,
  "kv_cache": null,
  "hardware": null,
  "verified": false,
  "verified_at": null,
  "probe": null,
  "notes": "Served through a LiteLLM gateway"
}
```

Committed profiles are named `*.example.json` and are always endpoint-free. Real
ones live in `inference/local/`, which is gitignored.

`bench probe <profile|endpoint>` does best-effort ground-truth capture and is never
required for a run to succeed:

- `GET /props` (llama.cpp) → `n_ctx`, `model_path`, `default_generation_settings`,
  build info. Stored raw in `probe`.
- `GET /v1/models`, `GET /health` → reachability and advertised ids.
- Sets `verified: true` and `verified_at` when something authoritative came back;
  otherwise records the failure. A profile that was never verifiable is displayed
  in the dashboard with an "unverified" badge, because an unverified Q5 claim is
  worth less than a verified one.

**Mismatch detection:** if the profile declares `context_window: 32768` but the
probe reports `n_ctx: 131072`, that is recorded as `inference.mismatch` and shown
prominently. This is the single most likely way a quant/ctx comparison goes wrong
and produces a plausible-looking but meaningless number.

## Architecture

Three layers, deliberately not mixed:

| Layer | Answers | Lifetime |
| --- | --- | --- |
| `benchmarks/<task>/` | What is the task, and how is it graded? | versioned |
| `runs/<id>/` | What happened on this attempt? | immutable once written |
| `dashboard/` | How do I read and compare it all? | disposable, regenerated |

```
<repo root>/
  README.md
  .env.example                       # committed; .env is not
  docs/superpowers/specs/            # this design
  prompts/                           # README committed, */ ignored
    README.md
    <user>/                          # private prompt drafts
  private/                           # never committed
    reference/tetris/                # the first run's implementation
    results/                         # local effort reports
  benchmarks/
    tetris/
      meta.json                      # version, artifact kind, grade command, turns
      TASK.md                        # canonical prompt, {{workspace}} placeholders
      RUBRIC.md                      # prose + a fenced json block of weights
      grader/                        # grade.js, engine.spec.js, browser.spec.js
      reference/                     # known-good build (this first run's output)
  inference/                         # named serving profiles
    *.example.json                   # committed, endpoint-free
    local/                           # gitignored, real endpoints
  runs/
    2026-10-26T07-04-05Z__tetris__internal-my-model__high__v1/
      run.json                       # the spine
      agentdir/                      # models.json + settings.json actually used
      transcript.jsonl               # pi session, verbatim
      events.jsonl                   # raw --mode json stream (per-message usage)
      workspace/                     # what the model built (cwd of the run)
      grading.json                   # per-rubric-item results
      screenshots/
      NOTES.md                       # human notes, never machine-written
  tools/
    bench                            # the CLI (Python 3, stdlib)
    lib/config.py                    # .env loading, ${VAR} expansion, redaction
    lib/sessionstats.py              # transcript/events -> effort accounting
    session-report.py                # thin CLI over the same module
    build-index.py                   # runs/*/run.json -> index.json + dashboard/data.js
    tests/                           # harness self-tests, with a fake pi
  dashboard/
    index.html  app.js  styles.css  data.js   # data.js is generated
  schemas/
    run.schema.json  benchmark.schema.json  inference.schema.json
```

### Why `run.json` is the spine

Every consumer — dashboard, `bench compare`, charts — reads `run.json` and nothing
else. No consumer needs to know how a run happened. That keeps the dashboard
disposable and the runner replaceable.

```json
{
  "id": "2026-10-26T07-04-05Z__tetris__internal-my-model__high__v1",
  "status": "ok",
  "benchmark": { "name": "tetris", "version": 1, "prompt_template_sha256": "…",
                 "prompt_sha256": "…", "rubric_sha256": "…", "grader_sha256": "…",
                 "prompt_source": "task" },
  "model": { "provider": "internal", "id": "my-model", "name": "Qwen3.8-Flash-Next" },
  "inference": {
    "profile": "gateway-q8", "runtime": "litellm",
    "endpoint": "***", "quantization": null,
    "declared_context_window": 262144, "served_context_window": null,
    "kv_cache": null, "verified": false, "mismatch": null
  },
  "agent": { "thinking": "high", "skills": true,
             "tools": ["bash", "edit", "read", "write"], "turn_mode": "replay",
             "context_window_override": null,
             "sampling": { "temperature": null, "seed": null, "source": "server default" } },
  "env": { "pi_version": "1.4.0", "node": "v26.12.1", "python": "3.13.1",
           "os": "darwin", "host": "…" },
  "timing": { "started": "…", "ended": "…", "wall_ms": 3726497,
              "model_ms": 2562000, "idle_ms": 672000, "ttft_ms": null },
  "effort": { "input": 13829562, "output": 82933, "reasoning": 71812,
              "total": 13912495, "calls": 135, "peak_context": 172335,
              "context_window": 262144, "cache_read": 0, "cost_usd": 0,
              "output_tps": 32.4, "prefill_tps": 5401.0, "cumulative": true },
  "turns": [ { "n": 1, "prompt_sha256": "…", "excerpt": "Create a web-based Tetris game",
               "started": "…", "ended": "…", "input": 17677 } ],
  "outcome": { "graded": true, "grader_error": null, "score": 1.0, "passed": 70,
               "failed": 0, "items": 70, "grader_confidence": "high",
               "human_interventions": 2, "stalled": true },
  "judge": null,
  "comparability_key": "…",
  "artifacts": { "transcript": "transcript.jsonl", "events": "events.jsonl",
                 "agentdir": "agentdir/", "workspace": "workspace/",
                 "screenshots": ["screenshots/desktop.png"] },
  "tags": [], "notes": ""
}
```

- `effort.cumulative: true` is the flag that stops 13.9 M being read as a context
  size. The dashboard always renders it as "cumulative over N calls".
- `output_tps` / `prefill_tps` are derived from `events.jsonl` timestamps and usage.
  For local models these are often the deciding number, not the score.
- `sampling.source` says whether temperature/seed came from us, the model config, or
  the server. Comparing runs with different sampling is flagged.

### Per-run agent directory (context window and sampling sweeps)

Verified working: `PI_CODING_AGENT_DIR` makes pi read `models.json` and
`settings.json` from a directory of our choosing, and a symlinked `auth.json`
authenticates normally.

So every run gets `runs/<id>/agentdir/` containing the *effective* config:

- `models.json` — a copy of the real one with the selected model's entry overridden:
  `contextWindow` (`--context-window`), `maxTokens` (`--max-tokens`), and
  `samplingParams` (`--temperature`, `--seed`; merged into every request body on
  OpenAI-compatible APIs, which the common gateways and local runtimes all are).
- `settings.json` — a minimal copy (provider/model/thinking, compaction settings).
- `auth.json` — symlink, never copied.

This buys three things: sweeps without editing global config, a reproducible record
of exactly what was sent, and an interpretable run even after `models.json` changes
underneath it. `--dry-run` prints the effective overrides.

**Caveat, recorded honestly:** a gateway may ignore `temperature`. The run stores
`sampling` as *requested*, and a probe or canary run is what upgrades it to
*confirmed*. Runs differing in requested sampling are flagged in comparisons.

### Grading contract

`benchmarks/<task>/meta.json`:

```json
{
  "name": "tetris",
  "version": 1,
  "artifact": "web-app",
  "entry_hints": ["index.html", "engine.js"],
  "grade": ["node", "grader/grade.js", "{workspace}"],
  "grade_timeout_s": 300,
  "requires": { "chrome": true },
  "turns": ["Create a web-based Tetris game", "`{{workspace}}` please", "…", "…"]
}
```

The grader receives the candidate workspace and prints **one JSON object on stdout**:

```json
{ "passed": 42, "failed": 0,
  "items": [ { "id": "srs-kicks", "ok": true, "detail": "I kicked 2 cells right" },
             { "id": "soft-drop-catchable", "ok": false, "detail": "60 rows/s" } ],
  "confidence": "high",
  "artifacts": { "screenshots": ["screenshots/desktop.png"] } }
```

- **Rubric weights live in one place:** `RUBRIC.md` carries prose plus a fenced json
  block of `{id, weight, kind}`. `bench` extracts it and computes `score` from the
  grader's item ids, so weights are never duplicated in code.
- A grader id with no rubric entry, or a rubric id the grader never reports, is a
  harness error and is surfaced, not ignored.
- Grader crash, non-zero exit, unparseable stdout or timeout ⇒ `graded: false`,
  `grader_error` set, `score: 0`. The run is still recorded.
- `confidence` is the grader's honesty flag: `low` when it had to guess the
  artifact's entry point. Shown as a badge.

### Judging (for rubric items tests cannot decide)

Machine grading decides Tetris. A judged task needs a model. **Constraint: this
work happens in Hong Kong, so OpenAI, Anthropic and Gemini models are unavailable.**
Judges must come from providers reachable here — which rules out the usual default
of "judge with Claude".

**Chosen judges** (all verified reachable, JSON mode and `temperature: 0` confirmed
with live calls):

| Role | Model | $ in/M | $ out/M | Why |
| --- | --- | --- | --- | --- |
| Primary | `deepseek/deepseek-v4-pro` | 0.96 | 1.91 | Strongest reasoning-per-dollar here; reachable via OpenRouter **and** our direct `deepseek` credential; returns clean JSON verdicts |
| Audit | `z-ai/glm-5.3` | 0.07 | 1.40 | Different family (Zhipu), so agreement is evidence rather than an echo; input cost is low enough to run on every judged item |
| Alternate | `moonshotai/kimi-k3.1-pro` | 2.00 | 10.00 | Long-context judge when the artifact itself is the input |
| Alternate | `minimax/minimax-m3` | 0.30 | 1.20 | Bulk passes over many runs |

Input price dominates judging cost (the artifact plus rubric is the prompt, the
verdict is tiny), which is why GLM-5.3's $0.07/M input makes it a cheap always-on
auditor. `z-ai/glm-5.3-prime` ($2.80/$8.80) is the escalation when the two judges
disagree and a human wants a third opinion.

Rules:

- **Judge model must never equal the model under test.** Enforced by `bench`, not by
  convention: a run whose judge matches its model is rejected. This is why the
  judge is recorded per run — if we ever benchmark a DeepSeek-family local model,
  the primary judge must switch to GLM, and the run must show that it did.
- **Judges must cite evidence.** A live probe exposed the failure mode: given an
  under-specified item, `deepseek-v4-pro` assumed a pass (4/4) while `glm-5.3`
  refused to score without evidence (0/4). The judge prompt must always include the
  artifact and require a quoted excerpt per verdict; a score without a citation is a
  prompt bug, not a verdict.
- Judges run at `temperature: 0` with a fixed prompt template whose hash is recorded
  (`judge.prompt_sha256`), so verdicts stay comparable over time.
- Judge cost and tokens are recorded in `run.json.judge`, **separately** from the
  run's own effort.
- **Verdict caching:** keyed by (artifact hash, rubric hash, judge model, judge
  prompt hash). Re-grading an old run never re-bills.
- Judging is opt-in per task (`meta.json.judge`), so machine-graded tasks cost
  nothing.

### `bench` CLI

```
bench run <task> --model <provider/id> [--inference <profile>] [--thinking L]
                 [--prompt <file>] [--turns single|replay] [--repeat N] [--tag TEXT]
                 [--baseline] [--context-window N] [--max-tokens N]
                 [--temperature T] [--seed S] [--timeout S] [--no-skills] [--dry-run]
bench suite <suite.json>        # matrix of tasks × models × profiles × repeats
bench probe <profile|endpoint>  # best-effort serving ground truth
bench import <session.jsonl> --task T --workspace DIR [--inference P] [--model …]
bench grade <run>               # re-run grading (uses cached judge verdicts)
bench judge <run>               # judge only, with caching
bench report <run>              # effort accounting for one run
bench annotate <run> --interventions N --note "…" [--baseline]
bench ls [--task T] [--model M] [--profile P] [--status S]
bench show <run>
bench compare <run> <run> [<run>…]
bench index                     # regenerate index.json + dashboard/data.js
```

`bench run` sequence:

1. Resolve task and inference profile; hash prompt, rubric, grader; mint the run id.
2. Create `runs/<id>/` with an empty `workspace/` (plus any `meta.json` seeds) and
   the generated `agentdir/`.
3. `--dry-run` prints the exact `pi` argv and the effective overrides, exits 0.
4. Launch `PI_CODING_AGENT_DIR=<run>/agentdir pi --print --mode json --model … 
   --thinking … --session-dir <run>/sessions` with **cwd = `workspace/`**, teeing
   stdout to `events.jsonl`.
5. `--turns replay` sends each turn in order, using `--continue --session <path>`
   for turns 2+ (verified: appends to one transcript).
6. On exit: copy the session to `transcript.jsonl`, run the grader, write
   `grading.json`, compute effort via `sessionstats`, assemble `run.json`, index.
7. Classify `status`: `ok`; `model_error` (non-zero exit or `error`/`aborted` stop
   reason); `timeout`; `empty` (no assistant text **and** no tool calls);
   `grader_error`; `endpoint_unreachable` (pre-flight probe failed).

Inputs the builder must source rather than invent:

- **Context window** for `effort.context_window`: from the effective `agentdir`
  entry (so an override is reflected), else `~/.pi/agent/models.json`, else `null`.
- **Imported config**: `bench import` derives provider/model/thinking from the
  session's `model_change` and `thinking_level_change` records, taking the last
  values before the first user message. The transcript wins over flags, and any
  disagreement is recorded.

Exit codes: `0` ok · `1` usage · `2` ran but grading failed · `3` model error ·
`4` endpoint unreachable.

### Suites, repeats and noise

Quantisation differences are often smaller than run-to-run sampling noise, so a
single run per config cannot support a claim.

```json
{
  "name": "local-model-quant-sweep",
  "task": "tetris",
  "repeats": 5,
  "turns": "replay",
  "thinking": "high",
  "inference": ["local-model-q8-litellm", "local-model-q5-litellm", "local-model-q4-litellm"]
}
```

`bench suite` runs the matrix sequentially, and the dashboard reports **median and
spread** per config, with an explicit *"difference is within run-to-run noise"*
verdict when the spreads overlap. It never prints a ranking from single runs.

### Effort accounting

`session-report.py` is refactored into `tools/lib/sessionstats.py` with
`summarize(session_path, events_path=None, since=None, until=None) -> dict`; the
existing script becomes a thin CLI so it keeps working standalone. `events.jsonl`
is the fallback and the source of throughput timing.

Per run: wall, model time, idle (human) time, input, output, reasoning, calls, peak
context and window, cache reads, cost, output tokens/s, prefill tokens/s. When a
provider reports `cost: 0` (as `internal` does), the dashboard says "cost not
reported" rather than "$0.00", and comparisons rank on tokens and time.

### Dashboard (v1)

Static page, no build step, no dependencies, same visual language as the Tetris
build. Data arrives as `dashboard/data.js` (`window.BENCH = {…}`, written by
`bench index`) because `fetch()` of local files is blocked under `file://`.
`runs/index.json` is written alongside for tooling.

- **Overview:** runs / configs / tasks counts, index freshness, last 10 runs.
- **Table:** task, model, inference profile, thinking, score, passed/failed, turns,
  interventions, tokens in/out, output tok/s, model time, wall, cost, date, status.
- **Filter/search:** task, provider, model, profile, thinking, status, score range;
  free text over prompt excerpt, tags, notes.
- **Grouping:** by task, then by model, then by inference profile — so a quant sweep
  reads as one experiment rather than N unrelated rows.
- **Compare:** 2–3 runs side by side, a per-rubric-item pass/fail matrix, and an
  explicit list of comparability differences (prompt hash, grader version, sampling,
  pi version, profile).
- **Charts:** canvas-drawn score vs. tokens, score vs. peak context, and score by
  profile with spread bars.
- **Run detail:** rubric items, screenshots, transcript path, workspace path,
  effective `agentdir` config, exact prompt text and hashes.
- **Guardrails:** "unverified profile" badge, "within noise" verdict, and a
  "single run, not a ranking" note where repeats are absent.

Starting runs from the UI is deliberately **not** in v1 — that is shell B, needing
only `POST /api/run` → `bench run` and `GET /api/events/<id>` → tail.

### Migrating the existing work

1. `benchmarks/tetris/reference/` ← the current artifact.
2. `benchmarks/tetris/TASK.md` ← the prompt from `benchmark/PROMPT.md`; the four
   original turns become `meta.json.turns`, with turn 2's path rendered as
   `{{workspace}}`.
3. `benchmarks/tetris/RUBRIC.md` ← the acceptance checklist with weights.
4. `benchmarks/tetris/grader/` ← `tests/engine.test.js` → `engine.spec.js` aimed at
   `{workspace}/engine.js`; `tests/browser-check.js` → `browser.spec.js`;
   `grade.js` orchestrates and emits the contract.
5. The first run's implementation and its effort report move to `private/`
   (`private/reference/tetris/`, `private/results/`), which is never committed.
6. `bench import` the existing session with that artifact as its workspace,
   producing run `…__v1` under `runs/`, which is also never committed. This proves
   `import` works on a real transcript; it does not publish the result.
7. `benchmark/` is removed; its prompt content becomes
   `benchmarks/tetris/TASK.md` and its accounting script becomes
   `tools/session-report.py`.

**Tolerant discovery matters.** A candidate may not name files `engine.js` or
`index.html`. The grader resolves the engine by `entry_hints`, then any
`engine.js`/`tetris*.js`, then `package.json.main`, loading it with a
`window`/`self` shim so UMD and plain-script styles both work. Failure to find a
loadable engine is `graded: false` + `confidence: "low"`, never a silent pass.

### Testing the harness itself

- `tools/tests/fixtures/fake-pi` — a stub emitting a canned `--mode json` stream and
  a synthetic session file, so the pipeline is exercised with **zero** model calls.
- `tools/tests/test_bench.py` — run-id minting, rubric extraction, run.json
  assembly, status classification, index building, tolerant discovery, effective
  `agentdir` generation, `--dry-run` argv equality, comparability keys.
- One manual end-to-end smoke per task on the cheapest config, documented.

### Risks

| Risk | Mitigation |
| --- | --- |
| Grader coupled to artifact structure | Tolerant discovery + `confidence` flag |
| Quant/ctx claims unverifiable | `bench probe`, `verified` flag, mismatch detection, dashboard badge |
| Gateway ignores sampling params | Record requested vs. confirmed; flag mismatches in comparison |
| Differences smaller than noise | `--repeat`, median + spread, "within noise" verdict |
| Prompt/grader drift breaks comparability | Version hashing + comparability key + explicit diff list |
| Endpoint down or model swapped underneath | Pre-flight probe; `endpoint_unreachable` status; profile pinned in the run |
| Surprise spend across 20 configs | `--dry-run`; judge caching; cost shown when reported |
| `file://` blocks local `fetch()` | Data embedded in `dashboard/data.js` |
| Chrome missing | `meta.json.requires.chrome`; clear grader error |
| Harness bugs found via costly runs | `fake-pi` self-tests, no model calls |

## Milestones

1. **Skeleton.** `git init`, layout, schemas, `bench` with `index`, `ls`, `show`,
   `probe`, and `run --dry-run`; `fake-pi` self-tests.
2. **Migrate Tetris.** TASK/RUBRIC/grader/reference, `inference/my-model-*`,
   `bench import` the first run, dashboard v1 reading it.
   *Deliverable: the existing run is browsable and graded.*
3. **The local-model comparison.** `bench run tetris --model internal/local-model`, graded and
   compared against run 1. *Deliverable: the first real comparison, on the model you
   asked for.*
4. **Sweeps.** `--context-window` / `--temperature` / `--seed`, `bench suite`,
   repeats, spread reporting, comparability guardrails.
5. **Docs.** README plus "how to add a benchmark" and "how to add an inference
   profile".

## Decisions already made

- Three-layer split (task / run / view); `run.json` is the spine.
- Approach A, with `bench` as the seam that makes B a thin shell.
- Four comparison axes, with inference profiles as first-class named objects and a
  comparability key that flags mixed comparisons.
- Python stdlib for `tools/`; graders may be any language.
- Rubric weights live in `RUBRIC.md`'s fenced json block, single source of truth.
- Grader lives with the benchmark; a candidate never grades itself.
- Per-run `agentdir/` via `PI_CODING_AGENT_DIR` for context-window and sampling
  sweeps, snapshotted for reproducibility.
- Prompts rendered with `{{workspace}}`; template and rendered hashes both recorded.
- Judges are Hong Kong-reachable: `deepseek/deepseek-v4-pro` primary, `z-ai/glm-5.3`
  audit (no OpenAI/Anthropic/Google). Temperature 0, evidence-citing prompts,
  cached by artifact+rubric+judge+prompt hash, cost tracked separately, and
  `judge ≠ model under test` enforced.
- The repo is public and ships no results: endpoints and keys live in `.env`,
  profiles reference `${VAR}`, committed profiles are `*.example.json`, run
  records are redacted, `agentdir/models.json` has `apiKey` stripped, `auth.json`
  is symlinked, and `runs/`, `private/` and `prompts/<user>/` are gitignored.
- `prompts/<user>/` holds private prompt drafts; `--prompt <file>` overrides the
  task's `TASK.md` and records `prompt_source: "private"`.
- Effort is cumulative-over-calls, labelled as such, with output/prefill tok/s.

## Left to the builder

- Field-level detail of the JSON schemas beyond the indicative shapes above.
- Chart styling and colour assignment in the dashboard.
- Exact judge prompt wording and score bands.
- Whether `tool_ms` is computed precisely or stays approximate.
- Seed fixtures for future long-context tasks (see Appendix B).

## Appendix A — example of a second task shape

Not a deliverable; here to prove the framework does not assume Tetris. A Periodic
Table explainer (all 118 elements, grouped by category, click-to-reveal, responsive)
has **no unit tests**, so its rubric items would be `kind: "judge"` and graded by the
OpenRouter judges. Its grader would be structural checks (boots with no console
errors, 118 cells, each with symbol and number, interaction mutates the DOM, fits
390 px) plus judged accuracy and clarity. This is the shape that forces `judge` to
be first-class rather than bolted on.

## Appendix B — long-context tasks

Your roadmap includes context windows, which is two different things:

1. **Serving window** — how many tokens the endpoint actually accepts. Handled by
   inference profiles and probing.
2. **Degradation with input length** — whether quality holds at 32k vs 128k. That is
   a *task* property: a task can ship seed fixtures (a large codebase, a long
   document) so the prompt's context load is the independent variable.

The design already supports it: seeds live in `meta.json`, `effort.peak_context` is
recorded per run, and the dashboard can plot score against peak context. No extra
machinery is needed now — only the tasks and fixtures, later.
