# Private prompts

Put prompt variants you do not want to publish here, one directory per person:

```
prompts/
  paul/
    tetris-strict-no-tests.md
    long-context-refactor.md
  alice/
    ...
```

Everything under `prompts/*/` is gitignored; only this README is committed. That
is deliberate — a benchmark prompt is often the interesting part, and you should
be able to iterate on one without publishing every draft.

## Using one

```sh
bench run tetris --model local/my-model --prompt prompts/paul/tetris-strict-no-tests.md
```

`--prompt` replaces the task's `TASK.md`. The run records `prompt_source` as
`private` and hashes the rendered text as usual, so the run is still internally
consistent — but note the consequence: a run whose prompt is not in the repo
**cannot be reproduced by anyone else**, and its `comparability_key` will not
match a run made from the published template. That is correct behaviour, not a
bug, and the dashboard says so on the run.

If a private prompt turns out to be worth sharing, move it into
`benchmarks/<task>/TASK.md` and bump the task version.
