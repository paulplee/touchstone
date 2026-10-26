# Inference profiles

An **inference profile** is a named description of how a model is *served*. Runs
reference a profile by name, so "which quantisation was that?" never depends on
remembering a URL, and a run stays interpretable after the endpoint changes.

Quantisation, context window and runtime are as much a variable as the model
itself. A profile is how that variable gets a name.

## Committed examples

`*.example.json` files are templates. They contain **no endpoints and no
credentials** — only `${VAR}` references resolved from `.env` at load time. Copy
one, rename it into `local/`, and fill in what you actually run:

```sh
cp inference/gateway-q8.example.json inference/local/my-gateway-q8.json
$EDITOR inference/local/my-gateway-q8.json
bench probe local/my-gateway-q8
```

`inference/local/` is gitignored. Keep your real profiles there.

## Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | Profile name, matching the filename stem |
| `runtime` | yes | What serves it — `litellm`, `llama.cpp`, `vllm`, `ollama`, … |
| `endpoint` | yes | Base URL, `/v1` included. Use `${VAR}` |
| `model_id` | yes | The id the endpoint expects |
| `quantization` | no | `Q8_0`, `Q5_K_XL`, `UD-Q4_K_M`, … as served |
| `context_window` | no | What the *server* was started with |
| `max_tokens` | no | Max output tokens |
| `kv_cache` | no | KV cache type, when it is worth recording |
| `hardware` | no | A short label for where it runs |
| `notes` | no | Anything a reader would need in six months |

## Verified or not

`bench probe` asks the endpoint for ground truth. llama.cpp answers `/props` with
`n_ctx` and `model_path`; a LiteLLM gateway usually answers `/v1/models` with
nothing but ids. Where something authoritative comes back, the profile is marked
verified — otherwise it is shown as **unverified** in the dashboard, because a
claimed quantisation nobody checked is worth less than one that was.

The probe also compares the declared `context_window` against what the server
actually reports. A profile that claims 32k while the server serves 128k is the
single most likely way a comparison goes wrong while still producing a
plausible-looking number, so a mismatch is recorded and displayed rather than
smoothed over.
