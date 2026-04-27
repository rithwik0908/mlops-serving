# Serving Options

This file is a lightweight reference for the supported serving modes in the repo.

## Classifier options

- PyTorch serving path
- optional ONNX backend
- optional quantized backend

The current integrated Zulip path uses the PyTorch classifier deployments in `staging`, `canary`, and `prod`.

## Generator options

- dummy mode for lightweight integration and fallback behavior
- seq2seq real mode
- causal or LoRA-backed real mode when configured

The current cluster uses the tiered generator deployments under `k8s/inference/`.

For production-style serving, the preferred path is the causal or LoRA-backed mode with
an MLflow registry alias such as `models:/tone-generator-lora@canary` or
`models:/tone-generator-lora@prod`.

## Practical recommendation

- use `staging` for low-risk validation
- use `canary` to validate the latest registered generator artifact and its serving latency
- use `prod` for the Zulip bridge target with the promoted `@prod` generator alias

## Serving notes

- The classifier path already resolves MLflow aliases directly.
- The generator path should do the same instead of relying on a manually mounted adapter path.
- The generator now benefits from stronger post-processing guards, but that still complements
  model quality rather than replacing better training data.
- Generator latency is lowest when the three tone rewrites are generated in one batched pass.
- Generator responses now expose whether each tone came from the model or from fallback rescue,
  which makes canary and rollback evaluation less ambiguous.
- Queue wait and inflight metrics now make generator saturation visible earlier than plain p95 latency.

## Important tradeoff

The current generator quality improvements rely partly on fallback cleanup logic. That improves bad outputs noticeably, but it is not a substitute for better training data or a stronger model.
