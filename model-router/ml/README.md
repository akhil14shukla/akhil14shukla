# Building the routing dataset

The classifier is easy. The dataset is the work, and it is the only part that
decides whether routing helps or hurts.

Everything here is offline. The router runs without any of it.

```bash
pip install -r ml/requirements.txt
```

## Why a learned model at all

The rule engine matches phrases, and no realistic word list separates these:

| prompt | rules | truth |
|---|---|---|
| `rename OrderService to OrderRecord in app/models.rb` | haiku | haiku |
| `rename OrderService to OrderRecord everywhere and keep the public API compatible` | sonnet | opus |
| `read src/queue.go and summarise it` | haiku | haiku |
| `read src/queue.go and work out why prod diverges from staging` | **haiku** | opus |

That fourth row is a real under-route: `read` matched the cheap lexicon and the
rest of the sentence was invisible. A 256-dimension static embedding separates
all four in **95 microseconds**, which is what makes it affordable in front of
every API call.

## The four sources of labels

```
taxonomy.py ──► seed.py    ──► seed.jsonl       synthetic, train-only
decisions.jsonl ► mine.py  ──► mined.jsonl      what actually happened
prompts.txt ──► label.py   ──► distilled.jsonl  Claude Opus 5, via Batch
by hand    ──► golden.py   ──► golden.jsonl     the only honest score
```

### 1. Seed — bootstrap when you have no logs

`taxonomy.py` is not a list of prompts. It is 24 task archetypes and 42
**minimal pairs**: near-identical wording on either side of a tier boundary,
so surface overlap actively punishes a keyword matcher.

```python
("rename {func} in {file}",                              "haiku",
 "rename {func} and update every call site in the package", "sonnet", "rename"),
```

Pairs cover all three boundaries. An early version had only haiku↔opus pairs,
and the resulting model separated "hard" from "not hard" cleanly while confusing
haiku with sonnet at close to chance. Adding the two missing boundaries cut
routing cost by more than half with no change to the model.

```bash
python3 ml/seed.py --per-template 8 --per-pair 5     # ~1,250 rows
```

### 2. Mined — the label you actually want

Not "what would a person call this" but *"what was the cheapest tier that
finished this turn cleanly"*. The decision log already knows:

| what happened | label | weight |
|---|---|---|
| escalated mid-turn | the tier it ended on | 0.9 |
| randomised, then finished clean | the tier used | 1.0 |
| finished clean, no escalation | the tier used | 0.5 |
| many steps, no escalation | the tier used | 0.3 |

```bash
python3 ml/mine.py --log ~/.claude/model-router/decisions.jsonl
```

**This data is biased, and the fix is one config line.** You only observe the
outcome for the tier you picked, so ordinary traffic confirms the policy that
produced it. Set `policy.explore_rate = 0.05` and the router sends one turn in
twenty to a neighbouring tier at random — clamped inside the floors, so a safety
rule is never overridden. Those rows are unbiased and are mined at full weight.
`mine.py` warns when a log has too few of them.

### 3. Distilled — buy a strong prior for about $20

```bash
python3 ml/label.py --prompts prompts.txt              # estimate, spends nothing
python3 ml/label.py --prompts prompts.txt --submit
python3 ml/label.py --prompts prompts.txt --collect batch_01xyz
```

Claude Opus 5 over the Batch API at 50% off. 5,000 prompts ≈ **$20**. Dry-run is
the default. Rows come back with the model's own confidence as their weight, and
anything under 0.6 is flagged — those sit on a boundary and are worth more of
your attention than the confident ones.

### 4. Golden — the only number you should believe

`golden.py` holds ~72 hand-labelled prompts, deliberately unlike the taxonomy:
lowercase, messy, referring to context the model cannot see. **They encode one
person's judgement.** Re-label them against your own traffic — it is the highest
value hour in this directory.

## The split policy is enforced in code, not documented in prose

`schema.split()` refuses the two ways this dataset can flatter itself:

- **seed rows are train-only.** Grading a model on the taxonomy that generated
  it measures nothing. `train.py` exits with an error if the test set is empty.
- **golden rows are test-only.**
- everything else is hashed by `group`, so all paraphrases of one prompt move
  together and no answer leaks across the split.

A test asserts golden prompts never appear verbatim in the seed set. It caught
two real leaks that were quietly inflating the score.

## Training

```bash
python3 ml/train.py --data 'ml/dataset/*.jsonl' --out ~/.claude/model-router/model.npz
```

It runs an ablation by default, because the question worth answering is whether
reading the prompt's meaning beats the signals the router already had.

Accuracy is not the headline. **Routing errors are asymmetric**: sending hard
work to a small model costs a retry and a bad answer; sending easy work to a big
one costs a few cents. `routing_cost` prices that at 1.0 per tier under-routed
against 0.3 per tier over-routed, and it is the number to optimise.

Measured on the 72 hand-labelled prompts, trained on seed data only:

| features | accuracy | macro F1 | under-route | over-route | routing cost |
|---|---|---|---|---|---|
| structural only (16d) | 0.458 | 0.375 | 0.542 | 0.000 | 0.653 |
| semantic only (256d) | 0.694 | 0.687 | 0.097 | 0.208 | 0.214 |
| **both (272d)** | **0.764** | **0.760** | **0.042** | 0.194 | **0.146** |

Structural signals alone are near-useless *on a fresh user turn* — every golden
row has no failures and no thrash, so the features are almost constant. They
earn their place mid-loop, which is exactly where the embedding is blind. The
two blocks are complementary, which is why `both` wins.

Gradient boosting (`--model gbt`, XGBoost when installed) ties on accuracy at
0.778 but scores **worse** on routing cost (0.171) because it under-routes more
than twice as often. Logistic regression also exports to plain numpy arrays,
so it is the default on both counts.

## Wiring the model into the router

```toml
[semantic]
enabled        = true
model_path     = "~/.claude/model-router/model.npz"
weight         = 0.6     # how far the model's margin can move the score
min_confidence = 0.45    # below this it abstains
```

The model enters as **one more score**, not a verdict:

```
delta = weight × (P(opus) − P(haiku))
```

That is deliberate. A model trained on someone else's traffic does not get to
override a floor — failing tool calls, an enabled thinking budget, and a context
past the ceiling all still win, and `!opus` in a prompt still beats everything.
Raise `weight` toward 1.0 once you trust it on your own data.

If numpy, model2vec, or the model file is missing, the scorer reports itself
unavailable and the router falls back to rules with no error. The 77-test suite
passes with nothing but the standard library installed.

## Which model to fine-tune, if you outgrow this

The default is `minishlab/potion-base-8M`: static embeddings, ~30 MB, a token
lookup plus a mean, 72 µs per prompt on a CPU with no torch loaded. In front of
every API call that budget is the whole design constraint.

| option | latency | when |
|---|---|---|
| **potion-base-8M static** (default) | ~0.1 ms | always start here |
| EmbeddingGemma-300M / Qwen3-Embedding-0.6B | ~10–30 ms CPU | if quality plateaus and you can afford it |
| ModernBERT-base fine-tuned end-to-end | ~10–20 ms CPU (ONNX) | the ceiling; 8k context lets you feed the tool-result tail |
| a sub-1B causal LM | 200 ms–2 s, needs a GPU | only if routing genuinely needs reasoning — then distil it back down |

Swap encoders with `--encoder`; the exported `.npz` records which one it was
trained with, and the runtime loads that unless overridden.

Before reaching for a bigger model, spend the effort on labels instead. Every
gain in the table above came from the dataset, not the classifier.
