# Touchstone

A local harness for benchmarking coding agents and the machines that serve them.

Touchstone exists to answer one question repeatedly and over years:

> Did this change to how I run a model — a different quantisation, a different
> context window, a different runtime, a different thinking level — make it better
> or worse at real work, and what did it cost in time and tokens?

It is built for locally hosted and gateway-served models, where the *serving
configuration* is as much a variable as the model itself.

## What is in this repo, and what is not

This repo is **code, task definitions and templates**. It deliberately does not
contain results.

| Committed | Not committed (yours to generate) |
| --- | --- |
| The harness in `tools/` | `runs/` — run records, stats, transcripts |
| Benchmark definitions: prompts, rubrics, graders | `private/` — your reference artifacts and reports |
| `inference/*.example.json` — endpoint-free templates | `inference/local/` — profiles naming a real host |
| `prompts/README.md` — the convention | `prompts/<you>/` — your private prompt drafts |
| `.env.example` | `.env` — endpoints and credentials |

The Tetris task ships as a **prompt template**, not as a finished app. Run it
against your own models and you get your own artifacts and your own numbers; the
first run's implementation lives in `private/` and is never published. Two reasons:
results are only meaningful next to the config that produced them, and a published
artifact is a spoiler for anyone about to try the same task.

## Quickstart

```sh
git clone https://github.com/<you>/touchstone && cd touchstone
cp .env.example .env && $EDITOR .env          # your endpoints
cp inference/gateway-q8.example.json inference/local/my-q8.json

bench probe local/my-q8                        # verify what the server really serves
bench run tetris --model <provider>/<model> --dry-run
bench run tetris --model <provider>/<model>
bench index && open dashboard/index.html
```

Requires Python 3.11+ (stdlib only — no installs), Node for the graders, and a
`pi` installation with credentials for whatever you benchmark.

## Shape

Three layers, deliberately not mixed:

| Layer | Answers | Lifetime |
| --- | --- | --- |
| `benchmarks/<task>/` | What is the task, and how is it graded? | versioned |
| `runs/<id>/` | What happened on this attempt? | immutable once written |
| `dashboard/` | How do I read and compare it all? | disposable, regenerated |

Every consumer reads `run.json` and nothing else, which is what keeps the
dashboard disposable and the runner replaceable.

## Why it is built this way

- **A candidate never grades itself.** The grader belongs to the benchmark, not to
  the artifact under test. The prompt tells the model to write its own tests; the
  grader ignores them and runs its own.
- **Serving config is first-class.** Named inference profiles record runtime,
  quantisation and context window, and `bench probe` captures ground truth where
  the endpoint exposes it, because a gateway's `/v1/models` usually tells you
  nothing.
- **Comparisons are guarded.** Runs hash their task version, prompt, grader, model,
  inference profile and sampling into a comparability key. Mixed comparisons are
  flagged rather than silently rendered.
- **Numbers are honest.** Token totals are cumulative over calls, never a context
  size, and a difference smaller than the run-to-run spread is reported as noise.
- **Secrets stay out.** Credentials live in `.env`; profiles reference `${VARS}`;
  run directories get a symlinked `auth.json` and a `models.json` with `apiKey`
  fields stripped.

## The first task: `tetris`

A self-contained browser Tetris, graded by headless rules tests and a real page
check in Chrome. See [`benchmarks/tetris/TASK.md`](benchmarks/tetris/TASK.md) for
why it is a good probe of agentic coding, and
[`benchmarks/tetris/RUBRIC.md`](benchmarks/tetris/RUBRIC.md) for the weighted
checklist.

## Documentation

- Design: [`docs/superpowers/specs/`](docs/superpowers/specs)
- Implementation plan: [`docs/superpowers/plans/`](docs/superpowers/plans)

## Licence

Not yet chosen.
