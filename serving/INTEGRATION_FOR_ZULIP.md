# Zulip Integration

This note describes the serving-side contract used by the Zulip bridge and UI integration.

## Main endpoints

### Classifier

`POST /predict`

Example request:

```json
{
  "message_id": "msg-1",
  "text": "please review this when you can",
  "message_type": "private"
}
```

### Generator

`POST /generate`

Example request:

```json
{
  "message_id": "msg-1",
  "text": "please review this when you can",
  "message_type": "private"
}
```

## In-cluster service targets

- production generator: `http://tone-generator-prod:8010/generate`
- production classifier: `http://classifier-pytorch-prod:8001/predict`
- bridge: `http://zulip-bridge:8090`

The bridge normally calls the generator only; the generator calls the classifier.

## Bridge endpoint

`POST /zulip/webhook`

This endpoint accepts Zulip-style payloads and returns Zulip-compatible markdown content with tone suggestions.

## Timeouts

- classifier request budget: a few seconds
- generator request budget: allow much longer than the classifier because real model loads and CPU generation are slower

## Validation

Use the cluster smoke path or call the bridge directly once `zulip-bridge` is ready.
