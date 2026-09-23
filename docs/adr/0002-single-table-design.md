# ADR 0002: DynamoDB single-table design with generic PK/SK

- **Status**: Accepted
- **Date**: 2026-09-23

## Context

The Projects API stores small, well-defined records (a project is a handful of scalar
attributes) and its access patterns are known up front:

1. Write a project and its name reservation atomically (S1).
2. Fetch a project by id (S2-201).
3. List one owner's projects, newest first, with pagination (S2-202).
4. Delete a project and release its name (S4-401).
5. React to new projects asynchronously through DynamoDB Streams (S4-402).

Later slices will add entity types that hang off a project (provisioning state, per-type
resources, possibly audit events). Traffic is bursty and low in absolute terms; there is no
operator who wants to browse the table by hand. The plan (`docs/PLAN.md`) already commits to
"DynamoDB single table" and the Terraform module `infra/terraform/modules/dynamodb_table` and the
repository `src/projects_api/repositories/projects.py` implement it; this ADR records why.

## Decision

One DynamoDB table per environment (`projects-api-<env>`) holds every entity type. Keys are
generic strings named `PK` (hash) and `SK` (range); the meaning of a key is carried by a prefix.

| Item | `PK` | `SK` | `entity` | Purpose |
|---|---|---|---|---|
| Project record | `PROJECT#<projectId>` | `META` | `PROJECT` | The project itself: `projectId`, `name`, `nameKey`, `type`, `status`, `ownerId`, `createdAt`, `updatedAt` |
| Name reservation | `NAME#<nameKey>` | `RESERVATION` | `NAME_RESERVATION` | Global uniqueness lock for a normalised name (see ADR 0003); stores `projectId`, `ownerId`, `createdAt` |

The **partition for a project is its id**. Anything that belongs to a project is written under
`PK = PROJECT#<projectId>` with a distinguishing `SK` (for example a future `PROVISION#<step>` or
`EVENT#<timestamp>`), so a single `Query` on the partition returns the record and everything
attached to it, and a `TransactWriteItems` can update several of them atomically. Every item
carries an `entity` attribute naming its type so stream consumers and future scans can filter
without parsing keys.

**GSI1** provides the owner listing. Project records set `GSI1PK = OWNER#<ownerId>` and
`GSI1SK = PROJECT#<createdAt>#<projectId>` (ISO 8601 timestamp, then id as a tiebreaker), with
`ProjectionType = ALL`. Listing a caller's projects is one `Query` on GSI1 with
`ScanIndexForward = false` and a `Limit`; the `LastEvaluatedKey` becomes the opaque cursor.
Reservation items do not set the GSI attributes and are therefore absent from the index (sparse
index), so listing never sees them.

**Adding an entity type** means:

1. Choose a new `PK` prefix (`PROJECT#`, `NAME#` are taken) or, for a child of a project, a new
   `SK` prefix under the project partition. Prefixes are uppercase nouns ending in `#`.
2. Set `entity` to a new constant and add the mapping functions next to `project_pk` /
   `name_pk` in the repository module.
3. If the type needs a new lookup, first try to express it through GSI1 by overloading
   `GSI1PK`/`GSI1SK` with a new prefix; only add GSI2 when the two access patterns genuinely
   collide on key shape.
4. No Terraform change is needed unless a new index is added; the table schema is only the four
   key attributes.

Operational settings, all in the Terraform module: `PAY_PER_REQUEST` (on-demand) billing,
point-in-time recovery enabled, server-side encryption with an AWS-owned key, deletion protection
on in `prod` (`deletion_protection = var.environment == "prod"` in `envs/dev/main.tf`), and an
opt-in stream (`stream_enabled`, `NEW_AND_OLD_IMAGES`) for the S4 provisioning pipeline. The
Lambda role is granted `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`,
`TransactWriteItems` and `ConditionCheckItem` on exactly this table ARN and `<arn>/index/*`;
`Scan` is deliberately not granted.

## Consequences

Positive:

- **Atomicity across entity types.** The project record and its name reservation live in the
  same table, so one `TransactWriteItems` creates or deletes both; cross-table transactions
  would work too but add latency and are easier to misuse. Future child items in the project
  partition get the same guarantee.
- **One thing to operate.** One set of alarms (`ddb-system-errors`, `ddb-throttled`), one
  PITR configuration, one IAM statement, one dashboard row, one on-demand bill. Adding a type
  adds no infrastructure.
- **Cheap, predictable reads.** Every access pattern is a key lookup or a single-partition
  `Query`; there are no scans and no joins. On-demand pricing means idle environments cost
  nothing beyond storage.
- **Schema evolution without migrations.** New attributes and new item types are additive;
  the table only knows about `PK`, `SK`, `GSI1PK`, `GSI1SK`.
- **Sparse GSI1 for free.** Only items that set `GSI1PK` appear in the index, so the owner
  listing never has to filter out reservations or other bookkeeping items.

Negative:

- **Keys are opaque.** `PK = PROJECT#prj_...` / `SK = META` says nothing without this document;
  the console is not a useful browsing tool. Mitigation: the `entity` attribute, the key
  functions in the repository module, and this ADR.
- **The GSI is overloaded.** `GSI1SK` mixes a timestamp and an id, and later entity types may
  reuse GSI1 with other prefixes. Sorting semantics must be documented per prefix, and a change
  to the sort key format (for example a different timestamp precision) requires rewriting
  existing items.
- **Hot partition risk is per project.** Because everything about a project shares a partition,
  a very chatty child type (high-frequency events) could concentrate writes. Projects are
  small today; if a child type becomes write-heavy, move it to its own prefix.
- **Blast radius.** A bad write path or an accidental delete affects all entity types at once.
  PITR, `prevent_destroy`-style deletion protection in prod, and least-privilege IAM (no `Scan`,
  no `DeleteTable`) limit this.
- **Tooling.** Generic single-table layouts are harder to feed into analytics or export tools
  than one table per entity; if reporting is needed, export via Streams rather than querying the
  table directly.

Compared with **one table per entity** (a `projects` table and a `name_reservations` table): that
layout is easier to read in the console and keeps IAM statements per entity, but the create path
would need a cross-table transaction, every new entity would need Terraform (table, PITR,
alarms, IAM), and the owner listing would still need a GSI. For a service whose entities are
tightly coupled and whose access patterns are all keyed, the single table is the smaller and
safer option.

## When to revisit

- A second access pattern per entity that cannot be expressed on GSI1 without ambiguity, or a
  need for a third index; consider GSI2 first, then a dedicated table.
- Any entity whose write rate is orders of magnitude above projects (metrics, logs, events);
  such data belongs in its own store or partition scheme.
- A requirement for ad-hoc analytics or operator browsing; add a Streams export rather than
  changing the table.
- A move to multi-region (Global Tables) or to provisioned capacity with autoscaling because
  on-demand costs exceed a steady baseline.
