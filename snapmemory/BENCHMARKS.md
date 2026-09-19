# BENCHMARKS.md

## How to run

UI: Performance tab → **Start Benchmark**.
API: `POST /api/benchmark/run`.
Export: Performance tab → **Export JSON**, or `GET /api/benchmark/export?format=json|csv`.

Every number is measured live against this machine and whatever is currently in your local
memory store — see `core/benchmark.py`. Nothing is pre-computed or hard-coded.

## What's measured

| Metric | What it measures |
|---|---|
| `embedding_throughput` | texts/sec embedding 50 fixed sample sentences with the active embedding provider |
| `retrieval_latency` | ms for one `retrieve()` call against your real corpus |
| `end_to_end_query_latency` | ms for a full `ask()` round trip (retrieval + answer generation), plus which model/execution provider actually ran |
| `chunking_throughput` | chars/sec for the sentence-aware chunker on a synthetic large text |

Each run also snapshots `device` (CPU, OS, ONNX Runtime providers, NPU detection) and
`model_statuses` (what's actually installed/active per capability) so a result is always
interpretable in context — a CPU-only run on a dev laptop should not be compared directly to
an NPU run on the target Snapdragon device.

## Example result (measured on the authoring dev machine — x86_64 Linux, CPU only, TF-IDF +
extractive answerer, no NPU present)

```json
{
  "embedding_throughput": {"value": 9997.39, "unit": "texts/sec"},
  "retrieval_latency": {"value": 1.55, "metric": "ms", "chunks_in_corpus": 17},
  "end_to_end_query_latency": {"value": 13.66, "metric": "ms", "execution_provider": "CPU"},
  "chunking_throughput": {"value": 15612445.4, "unit": "chars_per_second"}
}
```

These numbers are real output from an actual run against the demo dataset — reproduce them
yourself with `python run.py`, click **Load Demo Data**, then **Start Benchmark**.

## On the target Snapdragon device

Re-run the same benchmark after completing `SNAPDRAGON_SETUP.md`. Expect (and record, don't
assume):

- Embedding throughput to change based on whether TF-IDF or an ONNX neural model is active —
  a neural model on NPU may be slower per-item than TF-IDF but produces meaningfully better
  retrieval quality on paraphrased queries.
- `end_to_end_query_latency`'s `execution_provider` field to read `NPU` once a Qualcomm
  provider is actually wired in and verified via `ai/providers.py::detect_device()`.

Do not report NPU numbers you have not personally measured on Snapdragon hardware — the
Performance tab exists specifically so you don't have to.
