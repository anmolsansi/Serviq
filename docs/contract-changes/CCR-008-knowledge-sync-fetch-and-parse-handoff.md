# CCR-008 — Knowledge sync fetch and parse handoff

- Status: Accepted
- Date: 2026-09-03
- Linear: OPE-313
- Architecture: ADR-023

## Contract change

V1.3.07 activates the previously reserved durable knowledge-sync worker boundary. It does not change any public HTTP API or database schema.

### Consumed event

Topic: `serviq.knowledge.sync.v1`

Consumer group: `serviq-worker-knowledge-sync-v1`

Payload remains exactly the ADR-021 contract:

```json
{
  "tenantId": "<uuid>",
  "sourceId": "<uuid>",
  "syncVersion": 1
}
```

The enclosing ADR-022 event envelope is required and the Kafka key equals `aggregateId`.

### Retry records

Topic: `serviq.knowledge.sync.v1.retry`

Headers:

- `serviq-attempt`: ASCII positive integer;
- `serviq-not-before-ms`: ASCII epoch milliseconds.

The three retry delays are 30 seconds, 5 minutes, and 30 minutes.

### Dead-letter records

Topic: `serviq.knowledge.sync.v1.dlq`

Header:

- `serviq-error-code`: stable safe ASCII code.

The original key/value are preserved so an operator can correlate the failed durable event without placing raw fetched content in broker metadata.

### Produced parser event

Topic/event type: `serviq.knowledge.parse.v1`

Schema version: `1`

Aggregate: `knowledge_document/<documentId>`

Payload:

```json
{
  "tenantId": "<uuid>",
  "sourceId": "<uuid>",
  "documentId": "<uuid>",
  "documentVersion": 1,
  "sourceType": "url|pdf|markdown|text",
  "rawObjectKey": "<tenant-scoped object key>",
  "canonicalUri": "<final URL or null>",
  "contentHash": "<lowercase sha256 hex>"
}
```

`correlation_id` is inherited from the consumed sync event and `causation_id` is the consumed event ID.

## Data placement

URL bytes use deterministic raw key:

`tenants/{tenantId}/knowledge/{sourceId}/sync/{syncVersion}/raw`

Uploaded PDF/Markdown/text bytes remain at the already-stored source object key and are read in place.

No raw bytes are stored in PostgreSQL event payloads or Kafka event values beyond the existing object locator.

## Compatibility

This change is additive. Existing V1.3.06 sync producers remain valid without modification. ADR-022 publishes the new parse outbox event using the same generic publisher. Future parsers must consume the exact `serviq.knowledge.parse.v1` contract above rather than infer object placement from undocumented conventions.

## Rollback

Disable the sync consumer before reverting code. There is no migration rollback. Existing durable records and object-storage artifacts remain valid obligations/artifacts and are not deleted automatically.
