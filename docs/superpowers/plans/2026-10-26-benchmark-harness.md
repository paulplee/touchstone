# Benchmark Harness Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local harness that runs a benchmark task against a chosen model config, grades the artifact with the benchmark's own grader, records everything needed to interpret the result years later, and makes it searchable in a static dashboard.

**Architecture:** Three layers that never mix: `benchmarks/<task>/` (task + grader), `runs/<id>/` (immutable evidence, `run.json` is the spine), `dashboard/` (disposable view). A Python-stdlib `bench` CLI shells out to `pi` for each run, generates a per-run agent config directory so context window and sampling can be swept, grades the resulting workspace, and writes one run record. Consumers read `run.json` only.

**Tech Stack:** Python 3.13 stdlib only (`argparse`, `subprocess`, `unittest`, `json`, `hashlib`, `http.server` for test fixtures). Node 26 for graders (no npm deps). Vanilla HTML/CSS/JS for the dashboard, no build step. `pi` 1.4.0 is invoked as a subprocess.

**Spec:** `docs/superpowers/specs/2026-10-26-benchmark-harness-design.md`

**Scope:** This is Plan 1 of 2, covering spec milestones 1–2 plus the `agentdir` mechanism from milestone 4 that belongs in the runner. It ends with the existing Tetris run imported, graded and browsable, and `bench run` able to produce a second run. Plan 2 covers `bench suite`, repeats/noise reporting, judging, and the second task — written after a real comparison, because its design depends on what that teaches.

## Global Constraints

- `tools/` is **Python 3 stdlib only**. No pip installs, no pytest, no requests, no `python-dotenv`. Tests run with `python3 -m unittest`.
- **Nothing secret may be committed, and no result may be committed.** Endpoints and keys live in `.env` (gitignored); committed profiles are `*.example.json` carrying `${VAR}` references; run records are redacted before writing; `runs/`, `private/` and `prompts/<user>/` are gitignored.
- Graders may be any language; `meta.json.grade` declares the command.
- The dashboard has **no build step and no dependencies**, and must work when opened as `file://`.
- `runs/<id>/` is **immutable once written**. Re-grading writes `grading.json` only.
- Consumers read `run.json` and nothing else. No consumer parses a transcript to render.
- `effort.cumulative` is always `true`; token sums are cumulative over calls, never a context size.
- Prompt rendering: `{{workspace}}` is substituted at launch; both `prompt_template_sha256` and `prompt_sha256` are recorded; fairness uses the rendered hash.
- `pi` is invoked as a subprocess only; never import pi internals.
- Exit codes: `0` ok · `1` usage · `2` ran but grading failed · `3` model error · `4` endpoint unreachable.
- Status values: `ok`, `model_error`, `timeout`, `empty`, `grader_error`, `endpoint_unreachable`.
- Chrome at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`, overridable with `CHROME`.
- No OpenAI, Anthropic or Gemini models anywhere (Hong Kong). Judges are out of scope for this plan.
- Every commit is small and its message names the task.

## Review Focus

The spec implies these conditions but no task's happy-path tests exercise them. Each line's test is added to the task that owns the code.

1. **A secret ending up in a written file** — an API key from `.env` copied into `run.json`, or a real endpoint committed in a profile. The repo is public, so this is the most expensive failure available. Expect: `redact` replaces any env secret value with `***` in every record; `agentdir/models.json` has `apiKey` and `headers` stripped; `auth.json` is a symlink; committed profiles contain only `${VAR}`. (Task 1, Task 3, Task 5)
2. **A run that produces no artifact at all** — model refuses, or writes outside the workspace. Expect: `graded: false`, `score: 0`, `status` in (`empty`,`model_error`), a written `run.json`, and exit code 3. Never a crash, never a silent pass. (Task 6, Task 7)
3. **An endpoint that is down** (a local runtime that is not running). Expect: probe returns `reachable: false` within the timeout, no exception, and the run is refused with `endpoint_unreachable` and exit code 4 rather than hanging. (Task 3, Task 6)
4. **A candidate whose files are named nothing like the reference** — no `engine.js`, no `index.html`. Expect: grader does not crash; it reports `confidence: "low"` and scores whatever it could load. (Task 7)
5. **A transcript that switches models mid-session** (the first Tetris run had four `model_change` records). Expect: import records the model that actually answered the last turn, not the first or last record blindly. (Task 12)
6. **A `RUBRIC.md` whose fenced json and grader items disagree** — grader reports an id the rubric lacks, or the rubric lists an id the grader never reports. Expect: surfaced as a harness error in `grading.json` and on stdout, not silently scored. (Task 2, Task 7)

Six rather than five: the repo became public after this plan's first draft, and a leaked credential outranks everything else here.

---

### Task 1: Repo skeleton, test harness, fake pi, hashing and run ids

**Files:**
- Create: `.gitignore`, `README.md`, `.env.example`, `schemas/run.schema.json` (stub), `tools/lib/__init__.py`
- Create: `tools/lib/config.py`, `tools/lib/hashing.py`, `tools/lib/runid.py`
- Create: `tools/tests/__init__.py`, `tools/tests/test_config.py`, `tools/tests/test_hashing.py`, `tools/tests/test_runid.py`
- Create: `tools/tests/fixtures/fake-pi` (executable)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `config.ConfigError(Exception)`
  - `config.load_env(repo_root: Path, environ: dict | None = None) -> dict` — parses `.env` if present; **an existing environment variable wins**
  - `config.expand(value: str, env: dict) -> str` — substitutes `${VAR}` and `${VAR:-default}`
  - `config.require(env: dict, *names: str) -> None` — raises `ConfigError` naming the missing variable, never a value
  - `config.redact(obj: Any, env: dict) -> Any` — replaces any string equal to a secret env value with `"***"`, recursively through dicts and lists
  - `config.is_secret(name: str) -> bool` — true for names matching `*KEY`, `*TOKEN`, `*SECRET`, `*PASSWORD`
  - `hashing.sha256_text(s: str) -> str` → `"sha256:<hex>"`
  - `hashing.sha256_file(path: Path) -> str`
  - `hashing.sha256_tree(dir: Path, names: list[str]) -> str` — sorted, path-and-content hashed
  - `runid.mint(task: str, provider: str, model: str, thinking: str, version: int, when: datetime | None = None, seq: int = 0) -> str`
  - `runid.parse(run_id: str) -> dict` with keys `task, provider, model, thinking, version, seq, utc`
  - `runid.slug(s: str) -> str` — lowercase, `[^a-z0-9]+` → `-`, trimmed
  - `fake-pi` contract: honours `--print --mode json --session-dir DIR --model M [--continue --session PATH] PROMPT`; writes a canned JSONL event stream to stdout including one assistant message with `usage`; creates or appends a synthetic session file in `DIR`; env knobs `FAKE_PI_FAIL=1` (exit 1), `FAKE_PI_NO_OUTPUT=1` (write nothing), `FAKE_PI_SLEEP=<seconds>`, `FAKE_PI_MODEL_SWITCH=1` (emit an extra `model_change` before answering).

- [ ] **Step 1: Write the failing tests**

`tools/tests/test_runid.py`:

`tools/tests/test_config.py`:

```python
def test_env_file_is_parsed_and_real_environment_wins(self):
    (self.root / ".env").write_text("A=1\n# comment\nB='quoted'\n")
    env = config.load_env(self.root, environ={"B": "from-env"})
    self.assertEqual(env["A"], "1")
    self.assertEqual(env["B"], "from-env")
    self.assertEqual(env["B_QUOTED"] if "B_QUOTED" in env else "quoted", "quoted")

def test_expand_substitutes_with_defaults(self):
    self.assertEqual(config.expand("${A}/v1", {"A": "http://h"}), "http://h/v1")
    self.assertEqual(config.expand("${MISSING:-fallback}", {}), "fallback")
    with self.assertRaises(config.ConfigError):
        config.expand("${MISSING}", {})

def test_require_names_the_variable_not_its_value(self):
    with self.assertRaises(config.ConfigError) as cm:
        config.require({"OTHER": "secret"}, "LITELLM_API_KEY")
    self.assertIn("LITELLM_API_KEY", str(cm.exception))
    self.assertNotIn("secret", str(cm.exception))

def test_redact_removes_secrets_everywhere(self):          # Review Focus 1
    env = {"LITELLM_API_KEY": "sk-live-123", "LITELLM_BASE_URL": "https://gw.example/v1"}
    rec = {"inference": {"endpoint": "https://gw.example/v1", "key": "sk-live-123"},
           "turns": [{"excerpt": "using sk-live-123"}]}
    out = config.redact(rec, env)
    self.assertEqual(out["inference"]["key"], "***")
    self.assertEqual(out["inference"]["endpoint"], "***")
    self.assertNotIn("sk-live-123", json.dumps(out))

def test_is_secret_matches_credential_names(self):
    self.assertTrue(config.is_secret("OPENROUTER_API_KEY"))
    self.assertTrue(config.is_secret("HF_TOKEN"))
    self.assertFalse(config.is_secret("LITELLM_BASE_URL"))
```

`tools/tests/test_runid.py`:

```python
def test_mint_is_parseable_and_round_trips(self):
    rid = runid.mint("tetris", "internal", "my-model", "high", 1,
                     when=datetime(2026, 10, 26, 7, 4, 5, tzinfo=timezone.utc))
    self.assertEqual(rid, "2026-10-26T07-04-05Z__tetris__internal-my-model__high__v1")
    self.assertEqual(runid.parse(rid)["model"], "my-model")
    self.assertEqual(runid.parse(rid)["seq"], 0)

def test_repeat_runs_get_a_suffix(self):
    a = runid.mint("tetris", "internal", "local-model", "high", 1, when=NOW, seq=0)
    b = runid.mint("tetris", "internal", "local-model", "high", 1, when=NOW, seq=2)
    self.assertNotEqual(a, b)
    self.assertEqual(runid.parse(b)["seq"], 2)

def test_slug_handles_slashes_dots_and_underscores(self):
    self.assertEqual(runid.slug("my-model.gguf-UD-Q5_K_XL"),
                     "my-model-gguf-ud-q5-k-xl")
    self.assertEqual(runid.slug("vendor/model-5.3"), "vendor-model-5-3")
```

`tools/tests/test_hashing.py`:

```python
def test_text_and_file_hash_agree(self):
    p = self.tmp / "a.txt"
    p.write_text("hello")
    self.assertEqual(hashing.sha256_file(p), hashing.sha256_text("hello"))
    self.assertTrue(hashing.sha256_text("hello").startswith("sha256:"))

def test_tree_hash_is_order_independent_and_content_sensitive(self):
    (self.tmp / "b.js").write_text("2")
    (self.tmp / "a.js").write_text("1")
    h1 = hashing.sha256_tree(self.tmp, ["a.js", "b.js"])
    h2 = hashing.sha256_tree(self.tmp, ["b.js", "a.js"])
    self.assertEqual(h1, h2)
    (self.tmp / "a.js").write_text("changed")
    self.assertNotEqual(h1, hashing.sha256_tree(self.tmp, ["a.js", "b.js"]))
```

`tools/tests/test_fake_pi.py`:

```python
def test_fake_pi_emits_usage_and_a_session_file(self):
    out = subprocess.run([FAKE_PI, "--print", "--mode", "json", "--session-dir", str(d),
                          "--model", "internal/local-model", "hello"], capture_output=True, text=True)
    self.assertEqual(out.returncode, 0)
    events = [json.loads(l) for l in out.stdout.splitlines() if l.strip()]
    self.assertTrue(any(e["type"] == "agent_settled" for e in events))
    asst = [e for e in events if e["type"] == "message_end" and e["message"]["role"] == "assistant"]
    self.assertGreater(asst[0]["message"]["usage"]["input"], 0)
    self.assertEqual(len(list(d.glob("*.jsonl"))), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s tools/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.lib.config'`, and `FileNotFoundError` for `fake-pi`.

- [ ] **Step 3: Implement the modules and the fixture**

`config.py`: read `.env` line by line, skipping blanks and `#` comments, splitting on the first `=`, stripping optional matching quotes. `load_env` starts from `environ or os.environ` and only fills keys that are absent. `expand` uses a regex for `${NAME}` and `${NAME:-default}`, and raises `ConfigError` on an unresolvable name. `redact` recurses through dicts and lists, replacing any string that exactly equals a value whose variable name passes `is_secret`.

`hashing.py`: `hashlib.sha256`, hex digest prefixed `sha256:`. `sha256_tree` sorts `names`, joins `f"{rel}\n{content}\n"` and hashes the result.

`runid.py`: `strftime("%Y-%m-%dT%H-%M-%SZ")` on the UTC datetime, then the four slugged fields and `v<version>`, appending `-<seq>` only when `seq > 0`. `parse` splits on `__` and reverses it, treating the trailing `-N` as `seq` when present.

`fake-pi`: a Python script with a shebang, `chmod +x`. It parses only the flags it needs, emits one `message_start`/`message_end` pair plus `agent_settled`, and writes a session JSONL containing `session`, `model_change`, `thinking_level_change`, `message` (user) and `message` (assistant) records matching the real format used in `~/.pi/agent/sessions/`. On `--continue --session PATH` it appends a second user/assistant pair to that file instead of creating a new one. `FAKE_PI_MODEL_SWITCH=1` emits a `model_change` to `internal/other-model` **after** the first assistant message, so the last record is not the answering model.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tools/tests -v`
Expected: PASS, 9 tests.

- [ ] **Step 5: Verify the ignore rules actually ignore**

Run: `mkdir -p runs/x private/y prompts/me inference/local && touch runs/x/run.json private/y/f .env prompts/me/p.md inference/local/p.json && git status --porcelain --ignored | grep -E "^!!" | wc -l && git status --porcelain | wc -l`
Expected: 6 ignored paths, and 0 untracked paths that are not ignored — i.e. every one of those files is invisible to git. Delete them afterwards.

- [ ] **Step 6: Commit**

```bash
git init && git add -A && git commit -m "task 1: repo skeleton, config and secrets, hashing, run ids, fake pi"
```

---

### Task 2: Task loader — meta, prompt rendering, rubric extraction

**Files:**
- Create: `tools/lib/task.py`, `tools/tests/test_task.py`
- Create: `tools/tests/fixtures/tasks/demo/{meta.json,TASK.md,RUBRIC.md}`

**Interfaces:**
- Consumes: `hashing.sha256_text`, `hashing.sha256_file`.
- Produces:
  - `task.RubricError(Exception)`
  - `task.Task` dataclass: `root: Path`, `name: str`, `meta: dict`, `task_md: str`, `rubric_md: str`
  - `task.load_task(root: Path, name: str) -> Task`
  - `Task.version -> int` (from `meta["version"]`)
  - `Task.turns() -> list[str]` (from `meta["turns"]`, else `[task_md]`)
  - `Task.render(text: str, workspace: Path) -> str`
  - `Task.rubric() -> list[dict]` — `[{"id","weight","kind"}]`, `kind in {"machine","judge"}`
  - `Task.validate_rubric() -> None` — raises `RubricError` on duplicate ids, missing/negative weight, unknown kind
  - `Task.prompt_hashes(workspace: Path) -> dict` — `{"prompt_template_sha256", "prompt_sha256"}`
  - `Task.grade_cmd(workspace: Path) -> list[str]`
  - `Task.grader_hashes() -> dict` — `{"rubric_sha256", "grader_sha256"}`

- [ ] **Step 1: Write the failing tests**

Fixture `tasks/demo/TASK.md` contains `Build a thing in {{workspace}}.` and `RUBRIC.md` contains prose plus a fenced ```` ```json ```` block `[{"id":"a","weight":2,"kind":"machine"},{"id":"b","weight":1,"kind":"judge"}]`.

```python
def test_render_substitutes_workspace_and_hashes_differ(self):
    t = task.load_task(FIXTURES, "demo")
    rendered = t.render(t.turns()[0], Path("/tmp/ws"))
    self.assertIn("/tmp/ws", rendered)
    self.assertNotIn("{{workspace}}", rendered)
    h = t.prompt_hashes(Path("/tmp/ws"))
    self.assertNotEqual(h["prompt_template_sha256"], h["prompt_sha256"])

def test_rubric_extracted_from_fenced_json_block(self):
    t = task.load_task(FIXTURES, "demo")
    self.assertEqual([r["id"] for r in t.rubric()], ["a", "b"])
    self.assertEqual(t.rubric()[0]["weight"], 2)

def test_duplicate_rubric_ids_raise(self):        # Review Focus 6
    with self.assertRaises(task.RubricError):
        task.load_task(BAD_FIXTURES, "dup").validate_rubric()

def test_missing_fenced_block_raises(self):
    with self.assertRaises(task.RubricError):
        task.load_task(BAD_FIXTURES, "norubric").rubric()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_task -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.lib.task'`.

- [ ] **Step 3: Implement `task.py`**

Extract the rubric with a regex for the first ```` ```json ... ``` ```` block and `json.loads` it. `load_task` reads `meta.json`, `TASK.md`, `RUBRIC.md` and raises `RubricError` with the offending path when any is missing. `render` is a plain `str.replace("{{workspace}}", str(workspace))`. `grader_hashes` hashes every file under `root/grader` via `sha256_tree`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_task -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/task.py tools/tests/test_task.py tools/tests/fixtures/tasks
git commit -m "task 2: task loader with prompt rendering and rubric extraction"
```

---

### Task 3: Inference profiles and probing

**Files:**
- Create: `tools/lib/inference.py`, `tools/tests/test_inference.py`
- Create: `inference/README.md`, `inference/gateway-q8.example.json`, `inference/local-llamacpp.example.json`
- Create: `schemas/inference.schema.json`

**Interfaces:**
- Consumes: `hashing`, `config.expand`, `config.load_env`.
- Produces:
  - `inference.ProfileError(Exception)`
  - `inference.load_profile(root: Path, name: str, env: dict) -> dict` — resolves `local/` first, then the root; expands `${VAR}` in every string field through `config.expand`
  - `inference.validate_profile(p: dict) -> None` — requires `name`, `runtime`, `endpoint`, `model_id`; optional `quantization`, `context_window`, `max_tokens`, `kv_cache`, `hardware`, `notes`
  - `inference.probe(endpoint: str, timeout: float = 5.0) -> dict` → `{"reachable": bool, "props": dict|None, "models": list[str]|None, "error": str|None, "at": str}`
  - `inference.mismatch(profile: dict, probe_result: dict) -> dict|None` → `{"field": "context_window", "declared": int, "served": int}`

- [ ] **Step 1: Write the failing tests**

```python
def test_probe_reads_llama_cpp_props(self):
    with stub_server({"/props": {"default_generation_settings": {"n_ctx": 131072}},
                      "/v1/models": {"data": [{"id": "local-model"}]}}) as url:
        r = inference.probe(url, timeout=2)
    self.assertTrue(r["reachable"])
    self.assertEqual(r["props"]["default_generation_settings"]["n_ctx"], 131072)
    self.assertEqual(r["models"], ["local-model"])

def test_unreachable_endpoint_returns_cleanly(self):    # Review Focus 3
    r = inference.probe("http://127.0.0.1:9/v1", timeout=1)
    self.assertFalse(r["reachable"])
    self.assertIsNotNone(r["error"])

def test_mismatch_detects_served_context_differing_from_declared(self):
    p = {"name": "x", "runtime": "llama.cpp", "endpoint": "http://h/v1",
         "model_id": "m", "context_window": 32768}
    r = {"reachable": True, "props": {"default_generation_settings": {"n_ctx": 131072}}}
    self.assertEqual(inference.mismatch(p, r),
                     {"field": "context_window", "declared": 32768, "served": 131072})

def test_missing_required_field_raises(self):
    with self.assertRaises(inference.ProfileError):
        inference.validate_profile({"name": "x"})

def test_profile_expands_env_and_refuses_a_missing_variable(self):
    p = self.write_profile("local/t.json", {"endpoint": "${GW}/v1"})
    self.assertEqual(inference.load_profile(self.root, "local/t", {"GW": "http://h"})["endpoint"],
                     "http://h/v1")
    with self.assertRaises(config.ConfigError):
        inference.load_profile(self.root, "local/t", {})

def test_committed_examples_carry_no_host_or_key(self):     # Review Focus 1
    for f in (self.root / "inference").glob("*.example.json"):
        text = f.read_text()
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("sk-", text)
```

The stub server is a `http.server` in a thread, defined once in the test module, answering the two paths and 404 otherwise.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_inference -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `inference.py` and write the two profiles**

`probe` uses `urllib.request` with the timeout, catches `Exception`, and never raises. Tries `/props` then `/v1/models` relative to the endpoint's scheme and host. `mismatch` compares `profile["context_window"]` against `props.default_generation_settings.n_ctx` when both are present.

Write `inference/README.md` (the profile convention, `local/` for real ones, verified vs unverified) and the two `*.example.json` files from the spec. **They must contain no host and no key** — only `${LITELLM_BASE_URL}`, `${LOCAL_LLAMA_BASE_URL}` and so on. `inference/local/` is gitignored; add the ignore rule if Task 1's `.gitignore` lacks it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_inference -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Verify against the real endpoint**

Run: `set -a && . ./.env && set +a && python3 -c "from tools.lib import inference, config; import os; print(inference.probe(os.environ['LITELLM_BASE_URL'], 8))"`
Expected: `reachable: True` and a `models` list. A local runtime that is not running gives `reachable: False`, which the unit test already covers.

- [ ] **Step 6: Commit**

```bash
git add tools/lib/inference.py tools/tests/test_inference.py inference schemas/inference.schema.json
git commit -m "task 3: inference profiles and endpoint probing"
```

---

### Task 4: Effort accounting — `sessionstats` module and CLI

**Files:**
- Create: `tools/lib/sessionstats.py`, `tools/tests/test_sessionstats.py`
- Modify: `tools/session-report.py` (becomes a thin CLI over the module)
- Create: `tools/tests/fixtures/session-sample.jsonl`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `sessionstats.NoTranscriptError(Exception)`
  - `sessionstats.summarize(session_path: Path | None, events_path: Path | None = None, since: str | None = None, until: str | None = None, context_window: int | None = None) -> dict`
  - Returned keys: `input, output, reasoning, total, calls, peak_context, context_window, cache_read, cost_usd, cumulative, wall_ms, model_ms, idle_ms, output_tps, prefill_tps, first_at, last_at`
  - `sessionstats.turns(session_path, since=None, until=None) -> list[dict]` — per-turn `{"n","excerpt","input","started","ended"}`

- [ ] **Step 1: Write the failing tests**

`session-sample.jsonl` holds 3 assistant messages with `usage` (`input` growing 1000, 5000, 9000; `output` 10 each) and `durationMs` 2000 each, one `user` message between the second and third.

```python
def test_summarize_sums_inputs_and_marks_cumulative(self):
    s = sessionstats.summarize(FIXTURE)
    self.assertEqual(s["input"], 15000)
    self.assertEqual(s["calls"], 3)
    self.assertEqual(s["peak_context"], 9000)
    self.assertTrue(s["cumulative"])

def test_throughput_is_derived_from_durations(self):
    s = sessionstats.summarize(FIXTURE)
    self.assertAlmostEqual(s["output_tps"], 30 / 6.0, places=3)

def test_since_until_narrow_the_window(self):
    s = sessionstats.summarize(FIXTURE, since="second prompt")
    self.assertEqual(s["calls"], 2)

def test_missing_session_falls_back_to_events(self):
    s = sessionstats.summarize(None, events_path=EVENTS_FIXTURE)
    self.assertEqual(s["calls"], 3)

def test_neither_source_raises(self):
    with self.assertRaises(sessionstats.NoTranscriptError):
        sessionstats.summarize(None, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_sessionstats -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Port the logic from `tools/session-report.py`**

Move the counting loops from the existing script into `summarize`, returning a dict instead of printing. Keep the `--since`/`--until` semantics (a user message containing the text opens the window). Compute `output_tps = output / (model_ms/1000)` and `prefill_tps = input / (model_ms/1000)`, guarding division by zero. Rewrite `tools/session-report.py` to import the module and print the same table it prints today.

- [ ] **Step 4: Run tests and the existing script to verify both pass**

Run: `python3 -m unittest tools.tests.test_sessionstats -v && python3 tools/session-report.py --since "Create a web-based Tetris" --until "I want to use this" | head -8`
Expected: PASS, 5 tests; the report still shows `in 13,829,562` and `peak 172,335`.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/sessionstats.py tools/tests/test_sessionstats.py tools/session-report.py tools/tests/fixtures/session-sample.jsonl
git commit -m "task 4: extract effort accounting into a module"
```

---

### Task 5: Per-run agent directory

**Files:**
- Create: `tools/lib/agentdir.py`, `tools/tests/test_agentdir.py`
- Create: `tools/tests/fixtures/agent-src/{models.json,settings.json}`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `agentdir.build(run_dir: Path, provider: str, model_id: str, overrides: dict, source_dir: Path) -> Path`
  - `overrides` accepts `context_window`, `max_tokens`, `temperature`, `seed` (all optional; `None` means leave as-is)
  - Writes `<run_dir>/agentdir/{models.json,settings.json}` and symlinks `auth.json`
  - `agentdir.effective(agentdir_path: Path, provider: str, model_id: str) -> dict` — the entry actually used, for `run.json`
  - `agentdir.overrides_applied(overrides: dict) -> dict` — echoes only the keys that were set

- [ ] **Step 1: Write the failing tests**

Fixture `agent-src/models.json` mirrors the real shape: `{"providers": {"internal": {"baseUrl": "...", "api": "openai-completions", "apiKey": "k", "models": [{"id": "local-model", "contextWindow": 262144, "maxTokens": 65536}]}}}`.

```python
def test_overrides_context_window_and_sampling(self):
    d = agentdir.build(self.run_dir, "internal", "local-model",
                       {"context_window": 32768, "temperature": 0, "seed": 42}, SRC)
    m = json.loads((d / "models.json").read_text())
    entry = m["providers"]["internal"]["models"][0]
    self.assertEqual(entry["contextWindow"], 32768)
    self.assertEqual(entry["samplingParams"], {"temperature": 0, "seed": 42})
    self.assertEqual(agentdir.effective(d, "internal", "local-model")["contextWindow"], 32768)

def test_unset_overrides_are_left_alone(self):
    d = agentdir.build(self.run_dir, "internal", "local-model", {"temperature": 0}, SRC)
    entry = agentdir.effective(d, "internal", "local-model")
    self.assertEqual(entry["contextWindow"], 262144)
    self.assertNotIn("seed", entry.get("samplingParams", {}))

def test_auth_is_symlinked_not_copied(self):
    d = agentdir.build(self.run_dir, "internal", "local-model", {}, SRC)
    self.assertTrue((d / "auth.json").is_symlink())

def test_credentials_are_stripped_from_the_generated_models_json(self):  # Review Focus 1
    d = agentdir.build(self.run_dir, "internal", "local-model", {}, SRC)
    text = (d / "models.json").read_text()
    self.assertNotIn("sk-secret", text)
    self.assertIsNone(agentdir.effective(d, "internal", "local-model").get("apiKey"))

def test_unknown_model_id_raises(self):
    with self.assertRaises(KeyError):
        agentdir.build(self.run_dir, "internal", "nope", {}, SRC)

def test_other_models_are_untouched(self):
    d = agentdir.build(self.run_dir, "internal", "local-model", {"context_window": 8192}, SRC)
    m = json.loads((d / "models.json").read_text())
    self.assertEqual(m["providers"]["internal"]["models"][1]["contextWindow"], 262144)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_agentdir -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `agentdir.py`**

Deep-copy `models.json`, find the matching provider and model entry, apply only the set overrides, write it. Write a minimal `settings.json` carrying `defaultProvider`, `defaultModel`, `defaultThinkingLevel`, and the source's `compaction` block when present. Symlink `auth.json` with `os.symlink`. Create the directory with `parents=True, exist_ok=True`.

**Strip credentials on the way through.** Remove every `apiKey` and `headers` value from the provider and model entries in the generated `models.json`, and from whatever `effective()` returns, because this file is a copy of a file that holds keys and it sits inside a run directory. `auth.json` supplies the real credentials at run time via the symlink.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_agentdir -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Verify against real pi**

Run: `PI_CODING_AGENT_DIR=<a built agentdir> pi --print --model internal/local-model --thinking off "Reply with exactly: ok"`
Expected: prints `ok`. This confirms the generated config authenticates and pi accepts it.

- [ ] **Step 6: Commit**

```bash
git add tools/lib/agentdir.py tools/tests/test_agentdir.py tools/tests/fixtures/agent-src
git commit -m "task 5: per-run agent directory for context window and sampling sweeps"
```

---

### Task 6: Runner — argv construction, turn replay, status

**Files:**
- Create: `tools/lib/runner.py`, `tools/tests/test_runner.py`

**Interfaces:**
- Consumes: `agentdir`, `task.Task`.
- Produces:
  - `runner.build_plan(pi_bin: str, model: str, thinking: str, session_dir: Path, turns: list[str], extra_flags: list[str]) -> list[list[str]]` — one argv per turn; turn 1 has no `--continue`, later turns add `--continue --session <path>` where `<path>` is filled by `runner.session_path(session_dir)`. `PI_CODING_AGENT_DIR` is **not** in the argv (it is an environment variable); the CLI sets it and prints it alongside the argv for `--dry-run`.
  - `runner.run(plan: list[list[str]], workspace: Path, events_path: Path, timeout: float, env: dict | None = None) -> dict` → `{"exit_code","timed_out","turns_completed","stdout_text","stderr_text"}`; `env` is merged over `os.environ`.
  - `runner.session_path(session_dir: Path) -> Path | None` — newest `*.jsonl` in the dir
  - `runner.classify_run(result: dict, session_path: Path | None, events_path: Path) -> str` — returns one of the status values
  - `runner.preflight(profile: dict | None) -> tuple[bool, str | None]`

- [ ] **Step 1: Write the failing tests**

Tests point `pi_bin` at the `fake-pi` fixture and set `PI_CODING_AGENT_DIR` to a temp dir.

```python
def test_turn_one_has_no_continue_and_later_turns_do(self):
    plan = runner.build_plan(FAKE_PI, "internal/local-model", "high", SD, ["one", "two"], [])
    self.assertNotIn("--continue", plan[0])
    self.assertIn("--continue", plan[1])
    self.assertIn("--session", plan[1])

def test_run_writes_events_and_reports_completion(self):
    r = runner.run(plan, self.ws, self.events, timeout=30)
    self.assertEqual(r["exit_code"], 0)
    self.assertFalse(r["timed_out"])
    self.assertEqual(r["turns_completed"], 2)
    self.assertTrue(self.events.read_text().strip())

def test_model_error_is_classified(self):                       # Review Focus 2
    r = runner.run(plan, self.ws, self.events, timeout=30)      # FAKE_PI_FAIL=1
    self.assertEqual(runner.classify_run(r, None, self.events), "model_error")

def test_no_output_is_empty_not_ok(self):                       # Review Focus 2
    r = runner.run(plan, self.ws, self.events, timeout=30)      # FAKE_PI_NO_OUTPUT=1
    self.assertEqual(runner.classify_run(r, None, self.events), "empty")

def test_timeout_is_reported_without_raising(self):
    r = runner.run(plan, self.ws, self.events, timeout=1)       # FAKE_PI_SLEEP=10
    self.assertTrue(r["timed_out"])
    self.assertEqual(runner.classify_run(r, None, self.events), "timeout")

def test_preflight_fails_fast_when_endpoint_is_down(self):       # Review Focus 3
    ok, why = runner.preflight({"endpoint": "http://127.0.0.1:9/v1"})
    self.assertFalse(ok)
    self.assertIn("unreachable", why)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_runner -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `runner.py`**

`build_plan` produces `[pi, "--print", "--mode", "json", "--model", model, "--thinking", thinking, "--session-dir", str(session_dir)] + extra_flags + [prompt]`, adding `--continue --session <newest>` to turns 2+. `run` executes each argv in order with `subprocess.run(..., cwd=workspace, timeout=timeout, capture_output=True, env={**os.environ, **(env or {})})`, appending stdout to `events_path` and stopping on the first non-zero exit or timeout. `classify_run` checks, in order: `timed_out` → `timeout`; non-zero exit → `model_error`; no assistant message and no tool call in `events_path` → `empty`; else `ok`. `preflight` returns `(False, "endpoint unreachable: …")` when `inference.probe` reports not reachable, and `(True, None)` when there is no profile.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_runner -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/runner.py tools/tests/test_runner.py
git commit -m "task 6: pi runner with turn replay, timeout and status classification"
```

---

### Task 7: Grader invocation and weighted scoring

**Files:**
- Create: `tools/lib/grader.py`, `tools/tests/test_grader.py`
- Create: `tools/tests/fixtures/graders/{good.js,bad-extra-id.js,crash.js,partial.js}`

**Interfaces:**
- Consumes: `task.Task`.
- Produces:
  - `grader.grade(task: Task, workspace: Path, run_dir: Path, timeout: float) -> dict` → `{"graded": bool, "grader_error": str|None, "passed": int, "failed": int, "items": list, "confidence": str, "artifacts": dict, "score": float, "validation_errors": list[str]}`
  - `grader.score(items: list[dict], rubric: list[dict]) -> float` — `sum(weight for ok) / sum(weight)`, `0.0` when the rubric is empty
  - `grader.validate_items(items: list[dict], rubric: list[dict]) -> list[str]` — unknown ids and unreported rubric ids
  - `grader.discover_confidence(workspace: Path, entry_hints: list[str]) -> str` — `"high"` when a hint file exists, `"low"` otherwise

- [ ] **Step 1: Write the failing tests**

The fixture graders are small Node scripts reading `process.argv[2]` and printing a fixed JSON object.

```python
def test_valid_grader_output_is_scored_by_rubric_weights(self):
    r = grader.grade(self.task_with_grader(GOOD), self.ws, self.run, timeout=30)
    self.assertTrue(r["graded"])
    self.assertEqual((r["passed"], r["failed"]), (1, 1))
    self.assertAlmostEqual(r["score"], 2 / 3, places=4)

def test_grader_crash_is_graded_false_with_score_zero(self):
    r = grader.grade(self.task_with_grader(CRASH), self.ws, self.run, timeout=30)
    self.assertFalse(r["graded"])
    self.assertEqual(r["score"], 0.0)
    self.assertIn("exit", r["grader_error"])

def test_grader_reports_unknown_id_is_a_validation_error(self):   # Review Focus 6
    r = grader.grade(self.task_with_grader(EXTRA_ID), self.ws, self.run, timeout=30)
    self.assertTrue(any("unknown" in e for e in r["validation_errors"]))

def test_rubric_id_the_grader_never_reports_is_a_validation_error(self):
    r = grader.grade(self.task_with_grader(PARTIAL), self.ws, self.run, timeout=30)
    self.assertTrue(any("never reported" in e for e in r["validation_errors"]))

def test_unfamiliar_workspace_scores_low_confidence(self):        # Review Focus 4
    empty = self.tmp / "empty"; empty.mkdir()
    self.assertEqual(grader.discover_confidence(empty, ["index.html"]), "low")
    self.assertEqual(grader.score([], []), 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_grader -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `grader.py`**

Resolve `task.grade_cmd(workspace)` (substituting `{workspace}`), run it with `cwd=task.root`, and parse the **last** line of stdout as JSON. Any non-zero exit, timeout, or `JSONDecodeError` sets `graded=False` and `grader_error`. `score` weights by `rubric` and is `0.0` when nothing passed. `validation_errors` comes from `validate_items`. Write `grading.json` into `run_dir` containing the returned dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_grader -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/grader.py tools/tests/test_grader.py tools/tests/fixtures/graders
git commit -m "task 7: grader invocation with weighted scoring and contract validation"
```

---

### Task 8: Run record, comparability key and status

**Files:**
- Create: `tools/lib/runrecord.py`, `tools/tests/test_runrecord.py`

**Interfaces:**
- Consumes: `runid`, `hashing`, `sessionstats`, `grader`, `inference`, `agentdir`.
- Produces:
  - `runrecord.comparability_key(rec: dict) -> str`
  - `runrecord.assemble(...) -> dict` — takes `run_id, task, model, inference, agent, env, timing, effort, turns, outcome, artifacts, tags` and returns the `run.json` dict with `status`, `judge: None` and `comparability_key` set
  - `runrecord.write(rec: dict, run_dir: Path) -> Path` — writes `run.json`
  - `runrecord.load(run_dir: Path) -> dict`
  - `runrecord.classify(...)` — re-exported from `runner` for one import site

- [ ] **Step 1: Write the failing tests**

```python
def test_key_changes_with_sampling_but_not_with_tags(self):
    a = rec(sampling={"temperature": 0})
    b = rec(sampling={"temperature": 0.7})
    self.assertNotEqual(runrecord.comparability_key(a), runrecord.comparability_key(b))
    c = rec(sampling={"temperature": 0}, tags=["smoke"])
    self.assertEqual(runrecord.comparability_key(a), runrecord.comparability_key(c))

def test_key_changes_with_grader_and_prompt_hashes(self):
    self.assertNotEqual(runrecord.comparability_key(rec(grader_sha="sha256:1")),
                        runrecord.comparability_key(rec(grader_sha="sha256:2")))

def test_effort_is_marked_cumulative(self):
    r = runrecord.assemble(**assemble_args(effort={"input": 100}))
    self.assertTrue(r["effort"]["cumulative"])

def test_round_trip_write_and_load(self):
    r = runrecord.assemble(**assemble_args())
    p = runrecord.write(r, self.run_dir)
    self.assertTrue(p.name == "run.json")
    self.assertEqual(runrecord.load(self.run_dir)["id"], r["id"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_runrecord -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `runrecord.py`**

`comparability_key` hashes a canonical JSON dump of only: `benchmark.name`, `benchmark.version`, `benchmark.prompt_sha256`, `benchmark.grader_sha256`, `benchmark.rubric_sha256`, `model.provider`, `model.id`, `inference.profile`, `agent.thinking`, `agent.skills`, `agent.tools`, `agent.turn_mode`, `agent.context_window_override`, `agent.sampling`, `env.pi_version`. Tags, timestamps and notes are excluded by construction. `assemble` fills defaults for missing sections so a partial run still writes a valid record.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_runrecord -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/runrecord.py tools/tests/test_runrecord.py
git commit -m "task 8: run record assembly and comparability key"
```

---

### Task 9: Index builder

**Files:**
- Create: `tools/lib/index.py`, `tools/tests/test_index.py`

**Interfaces:**
- Consumes: `runrecord.load`.
- Produces:
  - `index.build(runs_dir: Path) -> dict` → `{"generated_at": str, "runs": [record, ...], "groups": {task: {model: {profile: [run_id]}}}}`
  - `index.write(idx: dict, index_path: Path, data_js_path: Path) -> None` — writes pretty JSON and `window.BENCH = {...};`
  - Runs with unreadable or missing `run.json` are skipped and listed under `idx["skipped"]`

- [ ] **Step 1: Write the failing tests**

```python
def test_groups_by_task_model_and_profile(self):
    self.write_run("r1", task="tetris", model="local-model", profile="local-model-q8-litellm")
    self.write_run("r2", task="tetris", model="local-model", profile="local-model-q8-litellm")
    self.write_run("r3", task="tetris", model="my-model", profile="flash-litellm")
    idx = index.build(self.runs_dir)
    self.assertEqual(len(idx["runs"]), 3)
    self.assertEqual(len(idx["groups"]["tetris"]["local-model"]["local-model-q8-litellm"]), 2)

def test_data_js_is_a_valid_assignment(self):
    self.write_run("r1")
    index.write(index.build(self.runs_dir), self.idx_path, self.data_js)
    text = self.data_js.read_text()
    self.assertTrue(text.startswith("window.BENCH = "))
    self.assertTrue(text.rstrip().endswith(";"))
    self.assertIn('"runs"', text)

def test_unreadable_run_is_skipped_not_fatal(self):
    (self.runs_dir / "broken").mkdir()
    (self.runs_dir / "broken" / "run.json").write_text("{not json")
    idx = index.build(self.runs_dir)
    self.assertEqual(idx["runs"], [])
    self.assertEqual(idx["skipped"], ["broken"])

def test_empty_runs_dir_is_fine(self):
    self.assertEqual(index.build(self.runs_dir)["runs"], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_index -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `index.py`**

Walk `runs_dir` one level deep, `json.load` each `run.json`, sort by `timing.started` descending. `data_js` is `"window.BENCH = " + json.dumps(idx, indent=1) + ";\n"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_index -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/index.py tools/tests/test_index.py
git commit -m "task 9: index builder for runs and dashboard data"
```

---

### Task 10: `bench` CLI wiring

**Files:**
- Create: `tools/bench` (executable), `tools/tests/test_cli.py`
- Modify: `tools/build-index.py` (thin CLI over `index`)

**Interfaces:**
- Consumes: every module above.
- Produces: `bench <subcommand>` with `run, probe, import, grade, report, annotate, ls, show, compare, index`, exit codes per Global Constraints, `--dry-run` on `run`, and `--prompt <file>` on `run` to override the task's `TASK.md` with a private prompt.

- [ ] **Step 1: Write the failing tests**

Tests invoke `tools/bench` as a subprocess with `PI_BIN` pointed at `fake-pi`.

```python
def test_dry_run_prints_the_exact_argv_and_exits_zero(self):
    r = run_bench("run", "tetris", "--model", "internal/local-model", "--dry-run")
    self.assertEqual(r.returncode, 0)
    self.assertIn("--mode json", r.stdout)
    self.assertIn("--session-dir", r.stdout)
    self.assertIn("agentdir", r.stdout)

def test_dry_run_shows_the_agentdir_environment_variable(self):
    r = run_bench("run", "tetris", "--model", "internal/local-model", "--dry-run")
    self.assertIn("PI_CODING_AGENT_DIR=", r.stdout)

def test_run_produces_a_run_json_with_a_status(self):
    r = run_bench("run", "demo", "--model", "internal/local-model")
    rec = json.loads(next(self.runs_dir.glob("*/run.json")).read_text())
    self.assertEqual(rec["status"], "ok")
    self.assertIn("comparability_key", rec)

def test_model_failure_exits_three(self):                        # Review Focus 2
    r = run_bench("run", "demo", "--model", "internal/local-model", env={"FAKE_PI_FAIL": "1"})
    self.assertEqual(r.returncode, 3)

def test_unreachable_endpoint_exits_four(self):                  # Review Focus 3
    r = run_bench("run", "demo", "--model", "internal/local-model",
                  "--inference", "dead-endpoint")
    self.assertEqual(r.returncode, 4)

def test_private_prompt_overrides_the_task_prompt(self):
    p = self.repo / "prompts" / "me" / "variant.md"
    p.parent.mkdir(parents=True); p.write_text("Do it differently in {{workspace}}.")
    run_bench("run", "demo", "--model", "internal/local-model", "--prompt", str(p))
    rec = json.loads(next(self.runs_dir.glob("*/run.json")).read_text())
    self.assertEqual(rec["benchmark"]["prompt_source"], "private")
    self.assertNotEqual(rec["benchmark"]["prompt_sha256"],
                        rec["benchmark"]["prompt_template_sha256"])

def test_index_writes_both_artifacts(self):
    run_bench("index")
    self.assertTrue((REPO / "runs" / "index.json").exists())
    self.assertTrue((REPO / "dashboard" / "data.js").exists())

def test_unknown_task_exits_one(self):
    self.assertEqual(run_bench("run", "nope", "--model", "internal/local-model").returncode, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_cli -v`
Expected: FAIL — `tools/bench` missing.

- [ ] **Step 3: Implement `tools/bench`**

`argparse` with one subparser per command. `run` orchestrates: load task → preflight → mint id → create run dir → build agentdir → build plan → `--dry-run` print and exit → run → grade → `summarize` → assemble → write → `index.write`. `--prompt` replaces the task's `TASK.md` text and sets `benchmark.prompt_source` to `"private"` (otherwise `"task"`); the rendered hash is computed either way, so the comparability key reflects the real prompt. Before writing any record, pass it through `config.redact(rec, env)`. `--dry-run` prints the argv, the `PI_CODING_AGENT_DIR` value, and the effective overrides. Map outcomes to exit codes with a single `EXIT = {"ok":0, "model_error":3, "timeout":3, "empty":3, "grader_error":2, "endpoint_unreachable":4}`. `annotate` writes `interventions`, `baseline` and `notes` back into `run.json` (the only sanctioned mutation). `ls`, `show` and `compare` print terminal tables.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_cli -v && python3 -m unittest discover -s tools/tests`
Expected: PASS, 6 tests; whole suite green.

- [ ] **Step 5: Commit**

```bash
git add tools/bench tools/tests/test_cli.py tools/build-index.py
git commit -m "task 10: bench CLI wiring all subcommands"
```

---

### Task 11: Tetris graders, validated by synthetic fixtures

**Files:**
- Verify: `benchmarks/tetris/{meta.json,TASK.md,RUBRIC.md}` — already written
- Create: `benchmarks/tetris/grader/grade.js`, `benchmarks/tetris/grader/engine.spec.js`, `benchmarks/tetris/grader/browser.spec.js`
- Create: `tools/tests/fixtures/tetris-min/{engine.js,index.html}` — a hand-written stub candidate
- Create: `tools/tests/fixtures/tetris-broken/engine.js` — the stub with a broken kick table
- Test: `tools/tests/test_tetris_grader.py`

**Interfaces:**
- Consumes: `task`, `grader`.
- Produces: a grader honouring the contract in the spec. `meta.json` and `RUBRIC.md` already exist; the grader's item ids must be exactly the 14 ids in `RUBRIC.md`'s fenced block.

**Why fixtures and not the reference implementation.** The repo is public and ships no
results, so the known-good artifact lives in `private/reference/tetris/` and is never
committed. Grading is validated publicly against small hand-written candidates that
satisfy some rubric items and fail others, which proves the pipeline end to end
without publishing a model's work. Validating against the real reference is a local
test that skips when `private/` is absent.

- [ ] **Step 1: Write the failing test**

```python
def test_grader_scores_the_synthetic_fixture_between_zero_and_one(self):
    r = grader.grade(task.load_task(BENCH, "tetris"), FIX / "tetris-min", self.run_dir, 300)
    self.assertTrue(r["graded"], r["grader_error"])
    self.assertEqual(r["confidence"], "high")
    self.assertGreater(r["score"], 0.0)
    self.assertLess(r["score"], 1.0)
    self.assertTrue(any(i["ok"] for i in r["items"]))
    self.assertTrue(any(not i["ok"] for i in r["items"]))

def test_grader_catches_a_broken_kick_table(self):
    r = grader.grade(task.load_task(BENCH, "tetris"), FIX / "tetris-broken", self.run_dir, 300)
    kicks = next(i for i in r["items"] if i["id"] == "srs-kicks")
    self.assertFalse(kicks["ok"])
    self.assertLess(r["score"], 1.0)

def test_grader_is_low_confidence_on_an_unfamiliar_workspace(self):   # Review Focus 4
    r = grader.grade(task.load_task(BENCH, "tetris"), self.empty_ws, self.run_dir, 300)
    self.assertEqual(r["confidence"], "low")
    self.assertFalse(r["graded"])

def test_grader_reports_exactly_the_rubric_ids(self):                 # Review Focus 6
    r = grader.grade(task.load_task(BENCH, "tetris"), FIX / "tetris-min", self.run_dir, 300)
    rubric_ids = {i["id"] for i in task.load_task(BENCH, "tetris").rubric()}
    self.assertEqual({i["id"] for i in r["items"]}, rubric_ids)
    self.assertEqual(r["validation_errors"], [])

@unittest.skipUnless((PRIVATE / "reference" / "tetris").exists(), "private reference not present")
def test_grader_passes_the_real_reference_implementation(self):
    r = grader.grade(task.load_task(BENCH, "tetris"), PRIVATE / "reference" / "tetris",
                     self.run_dir, 600)
    self.assertTrue(r["graded"], r["grader_error"])
    self.assertEqual(r["failed"], 0)
    self.assertEqual(r["score"], 1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tools.tests.test_tetris_grader -v`
Expected: FAIL — `benchmarks/tetris/grader/grade.js` missing.

- [ ] **Step 3: Write the synthetic fixtures**

`tetris-min/engine.js`: a UMD module exporting a minimal `TetrisEngine` with the
correct 7-bag and rotation states but a wrong soft-drop rate and no T-spin
detection, plus an `index.html` that loads it. It should pass `bag-7`,
`rules-are-testable`, `page-boots` and fail `soft-drop-catchable`, `scoring` and the
rest. `tetris-broken/engine.js`: `tetris-min` with the I-piece kick table replaced by
`[[0, 0]]`.

- [ ] **Step 4: Write the graders**

`engine.spec.js`: load the candidate engine by `entry_hints`, then any
`engine.js`/`tetris*.js`, then `package.json.main`, inside a `vm` context shimmed with
`window`, `self` and `module` so UMD and plain-script both work; run the assertions
from the first run's rules suite against it, emitting one item per rubric id.
`browser.spec.js`: the page checks, using `CHROME` with the macOS default.
`grade.js`: run both, merge items, set `confidence` from `discover_confidence`,
copy screenshots into `artifacts`, print one JSON object. A missing Chrome is a
grader error, not a crash.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_tetris_grader -v`
Expected: PASS. The synthetic fixture scores strictly between 0 and 1; the broken
one fails `srs-kicks`; the reference test is skipped unless `private/` exists.

- [ ] **Step 6: Confirm nothing private is staged**

Run: `git status --porcelain`
Expected: only `benchmarks/tetris/grader/*` and `tools/tests/fixtures/tetris-*` — no
`private/`, no `runs/`.

- [ ] **Step 7: Commit**

```bash
git add benchmarks/tetris/grader tools/tests/fixtures/tetris-min tools/tests/fixtures/tetris-broken tools/tests/test_tetris_grader.py
git commit -m "task 11: tetris graders validated by synthetic fixtures"
```

---

### Task 12: Import the first run

**Files:**
- Create: `tools/tests/test_import.py`
- Modify: `tools/lib/runner.py` (add `derive_config(session_path) -> dict`)
- Modify: `tools/bench` (implement `import`)

**Interfaces:**
- Consumes: everything above.
- Produces: `runner.derive_config(session_path: Path) -> dict` → `{"provider","model","thinking"}` from the transcript; `bench import` writes a complete run record for an existing session.

- [ ] **Step 1: Write the failing tests**

```python
def test_derives_the_model_that_answered_the_last_turn(self):    # Review Focus 5
    cfg = runner.derive_config(FIXTURE_WITH_LATE_SWITCH)
    self.assertEqual(cfg["model"], "answered-model")
    self.assertTrue(cfg["disagreement"], "a later model_change should be flagged")

def test_derives_thinking_from_the_last_change(self):
    self.assertEqual(runner.derive_config(FIXTURE_THINKING).get("thinking"), "high")

@unittest.skipUnless(REAL_SESSION.exists(), "no transcript supplied on this machine")
def test_import_of_a_transcript_records_its_turns_and_effort(self):
    run_bench("import", str(REAL_SESSION), "--task", "tetris",
              "--workspace", str(PRIVATE / "reference" / "tetris"),
              "--inference", "local/reference")
    rec = json.loads(next(self.runs_dir.glob("*/run.json")).read_text())
    self.assertGreaterEqual(len(rec["turns"]), 1)
    self.assertTrue(rec["effort"]["cumulative"])
    self.assertGreater(rec["effort"]["input"], 0)
    self.assertEqual(rec["benchmark"]["name"], "tetris")
    self.assertNotIn("sk-", json.dumps(rec), "no credential may reach a run record")
```

No magic numbers from one private transcript: the test asserts structure, so it stays
meaningful on any machine and publishes nobody's totals.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tools.tests.test_import -v`
Expected: FAIL — `derive_config` missing, `import` unimplemented.

- [ ] **Step 3: Implement `derive_config` and `import`**

`derive_config` scans the session for `model_change` and `thinking_level_change` records, but returns the provider/model from the **last assistant message** (which is what actually answered), falling back to the last `model_change` when there is none, and warns on mismatch by returning `{"...": ..., "disagreement": True}`. `bench import` builds the same record shape as `run` but from a supplied transcript and workspace: effort via `summarize`, grading via `grade`, turns from the session's user messages, and `status` from `classify_run` against the existing events (absent events ⇒ `ok` when the transcript has assistant output).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tools.tests.test_import -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Import a real run locally and index it**

```bash
python3 tools/bench import "$TOUCHSTONE_SESSION" \
  --task tetris --workspace private/reference/tetris --inference local/reference
python3 tools/bench ls
```
Expected: one run listed with a score and a non-zero cumulative input figure.
`$TOUCHSTONE_SESSION` is a path to a pi session transcript; nothing about it is
published, and `runs/` is gitignored.

- [ ] **Step 6: Confirm nothing private is staged**

Run: `git status --porcelain`
Expected: `tools/` changes only. No `runs/`, no `private/`, no `.env`.

- [ ] **Step 7: Commit**

```bash
git add tools
git commit -m "task 12: import an existing transcript as a run"
```

---

### Task 13: Dashboard

**Files:**
- Create: `dashboard/index.html`, `dashboard/app.js`, `dashboard/styles.css`
- Create: `dashboard/data.js` (generated; **gitignored**, since it is derived from your private runs). A committed `dashboard/data.example.js` with one synthetic run lets the page render before the first `bench index`
- Create: `dashboard/data.example.js` — one synthetic run, committed, so the page renders on a fresh clone
- Create: `tools/tests/dashboard-check.js` (plain Node, headless Chrome over CDP, in the style of the Tetris `browser-check.js`)

**Interfaces:**
- Consumes: `window.BENCH` from `dashboard/data.js`, falling back to `data.example.js` when the generated file is absent (`{generated_at, runs, groups}`).
- Produces: a static page with overview counts, a sortable run table, filters (task, provider, model, profile, thinking, status, score range) and free-text search, a 2–3 run compare view with a per-rubric-item pass/fail matrix, canvas charts (score vs tokens, score vs peak context), and a run detail view.

- [ ] **Step 1: Write the failing check**

`tools/tests/dashboard-check.js` asserts, via CDP: the page loads with no console errors; `#run-count` shows the number of runs in the loaded data; typing a model name into `#search` reduces `#runs tbody tr` to the matching rows; clicking a row opens the detail view showing the run id and rubric item count; selecting two runs and pressing Compare renders a matrix with a cell per rubric item; the layout has no horizontal overflow at 390 px. It runs against `data.example.js` so it needs no real runs, and writes `tools/tests/dashboard.png`.

- [ ] **Step 2: Run the check to verify it fails**

Run: `node tools/tests/dashboard-check.js`
Expected: FAIL — `dashboard/index.html` not found.

- [ ] **Step 3: Implement the dashboard**

Vanilla JS, no modules, no build step, same visual language as the Tetris build. Read `window.BENCH` directly (never `fetch`). Load `data.js` with `onerror` falling back to `data.example.js`, so a fresh clone shows the interface with sample data and a clear "sample data" banner rather than an empty page. Render the table from `runs`, grouping rows by task → model → profile when no filter is active. Charts drawn on `<canvas>`. The compare matrix colours each rubric item green/red/grey (grey = not reported). Show an "unverified" badge when `inference.verified` is false, a "low confidence" badge when `outcome.grader_confidence` is `"low"`, and a banner listing comparability-key differences when selected runs differ.

- [ ] **Step 4: Run the check to verify it passes**

Run: `node tools/tests/dashboard-check.js`
Expected: all assertions pass, `dashboard.png` written.

- [ ] **Step 5: Commit**

```bash
git add dashboard tools/tests/dashboard-check.js
git commit -m "task 13: static dashboard for browsing and comparing runs"
```

---

### Task 14: README and how-to docs

**Files:**
- Modify: `README.md`
- Create: `docs/how-to-add-a-benchmark.md`, `docs/how-to-add-an-inference-profile.md`

**Interfaces:**
- Consumes: everything.
- Produces: the operator documentation.

- [ ] **Step 1: Update the README**

Keep the existing public/private table and shape sections. Add: the `bench` quickstart
(`probe`, `run --dry-run`, `run`, `ls`, `show`, `compare`, `index`); how to open the
dashboard from `file://`; the test commands (`python3 -m unittest discover -s tools/tests`,
`node tools/tests/dashboard-check.js`); the private-prompts convention; and the
effort-accounting caveat that token totals are cumulative over calls while the pi
status bar shows only the current context.

- [ ] **Step 2: Write the two how-to docs**

`how-to-add-a-benchmark.md`: create the directory, write `TASK.md` with
`{{workspace}}`, `meta.json` with turns and the grade command, `RUBRIC.md` with the
fenced json block, a grader emitting the contract, and **synthetic fixtures that
prove the grader without publishing a real artifact**. Show a worked example with a
one-item rubric. `how-to-add-an-inference-profile.md`: copy an example, fill
`runtime`, `endpoint`, `model_id`, `quantization`, `context_window`; run `bench probe`;
fix any mismatch it reports; confirm the profile contains no literal host.

- [ ] **Step 3: Verify the documented commands actually work**

Run each command in the README verbatim in order, on a clean clone into a temp dir.
Expected: every one succeeds, with no steps requiring unstated knowledge, and
`git status` in the clone stays clean after the run (nothing generated is tracked).

- [ ] **Step 4: Commit**

```bash
git add README.md docs
git commit -m "task 14: operator documentation"
```

---

## Self-Review

**1. Spec coverage.** Every spec section maps to a task: the three-layer split and `run.json` spine → Tasks 8, 9, 13; comparison axes and comparability key → Task 8; inference profiles and probing → Task 3; per-run agentdir → Task 5; grading contract and weighted rubric → Tasks 2, 7, 11; `bench` CLI and exit codes → Task 10; **Public and private** (`.env`, `${VAR}` expansion, redaction, gitignored `runs/`+`private/`+`prompts/<user>/`, example profiles) → Tasks 1, 3, 5, 11, 13, 14; suites/repeats/noise → **deferred to Plan 2** (stated in Scope); judging → **deferred to Plan 2**; effort accounting → Task 4; dashboard → Task 13; Tetris task definition → written already, graded in Task 11; harness self-tests → Task 1 and every task's tests; risks table → covered by the Review Focus tests and Task 3's mismatch detection.

Two deliberate deviations from the spec's original file list, both forced by the repo going public: `benchmarks/tetris/reference/` is not committed (it lives in `private/`), and `dashboard/data.js` is gitignored with a committed `data.example.js` in its place.

**2. Step scan.** Each step names one action with a checkable result. Code bodies appear only where the signature and tests leave a choice (the fake-pi contract, `discover_confidence`'s fallback order, the comparability-key field list, the vm shim), because those are the decisions an implementer cannot make alone.

**3. Type consistency.** `sha256_*` names are used identically in Tasks 1, 2 and 8. `Task` methods are defined in Task 2 and consumed with the same names in Tasks 7, 10 and 11. `classify_run` is defined in Task 6 and re-exported in Task 8 under the same name. `grade()`'s return keys are the ones Task 8's `assemble` reads. `effective()` from Task 5 is what Task 8 records as `agent`. `sessionstats.summarize` keys match the `effort` block in the spec's schema verbatim.

**4. Review Focus.** All six lines have a named test in an owning task: 1 secrets → Task 1 (`test_redact_removes_secrets_everywhere`), Task 3 (`test_committed_examples_carry_no_host_or_key`), Task 5 (`test_credentials_are_stripped_from_the_generated_models_json`); 2 no artifact → Task 6 (`test_model_error_is_classified`, `test_no_output_is_empty_not_ok`), Task 7 (`test_grader_crash_is_graded_false_with_score_zero`), Task 10 (`test_model_failure_exits_three`); 3 endpoint down → Task 3 (`test_unreachable_endpoint_returns_cleanly`), Task 6 (`test_preflight_fails_fast_when_endpoint_is_down`), Task 10 (`test_unreachable_endpoint_exits_four`); 4 unfamiliar workspace → Task 7 (`test_unfamiliar_workspace_scores_low_confidence`), Task 11 (`test_grader_is_low_confidence_on_an_unfamiliar_workspace`); 5 model switch mid-session → Task 12 (`test_derives_the_model_that_answered_the_last_turn`); 6 rubric/grader disagreement → Task 2 (`test_duplicate_rubric_ids_raise`), Task 7 (`test_grader_reports_unknown_id_is_a_validation_error`), Task 11 (`test_grader_reports_exactly_the_rubric_ids`).

**5. Proportion.** The spec is 380 lines; this plan is longer but is mostly signatures, test names and commands rather than program bodies, which is the ratio the skill asks for.
