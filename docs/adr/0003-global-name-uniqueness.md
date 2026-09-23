# ADR 0003: Global, case-insensitive project name uniqueness via a reservation item

- **Status**: Accepted
- **Date**: 2026-09-23

## Context

A project's `name` is chosen by the user and will later be turned into a DNS label or hostname
(for example `<name>.projects.example`) when provisioning arrives in Slice 4. DNS names are
case-insensitive and must be unique within their zone, so two users cannot both own
`My-Agent` and `my-agent`, and a name cannot be scoped per owner. The product decision recorded
in `docs/PLAN.md` is therefore: names are **globally** unique and compared
**case-insensitively**; `POST /v1/projects` returns `201` on success and `409` if the name is
taken.

DynamoDB enforces uniqueness only on a table's primary key. It has no unique secondary indexes
and no cross-item constraints, so uniqueness on an attribute that is not the primary key has to be
designed in. The project record itself is keyed by `PROJECT#<projectId>` (ADR 0002), so the name
is not part of any primary key.

## Decision

### Normalisation

`domain/validation.py` is the single source of the rules:

- `normalise_name(raw)` trims leading and trailing whitespace and collapses runs of internal
  whitespace to a single space. This is the **display name** stored in `name`; case is preserved.
- `validate_name(raw)` normalises, then requires 3 to 63 characters matching
  `^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$` (letters, digits, spaces, hyphens, underscores;
  alphanumeric at both ends), rejecting anything else with a `400`.
- `name_key(name)` is `normalise_name(name).lower()`: the **uniqueness key**. `"My  Project"`,
  `"my project"` and `" MY PROJECT "` all have the key `my project`.

The character set is a superset of a DNS label (spaces and underscores are allowed). Mapping a
name to a hostname (for example replacing spaces and underscores with hyphens) is deferred to the
provisioning design (S4-403, ADR 0005) and may introduce a second, stricter key at that point.

### Reservation item

Every project has a companion item in the same table:

```text
PK = NAME#<nameKey>   SK = RESERVATION   entity = NAME_RESERVATION
projectId, ownerId, createdAt
```

Because `NAME#<nameKey>` is a primary key, DynamoDB itself guarantees that at most one such
item exists per normalised name.

### One transaction, two conditional puts

`ProjectRepository.create` writes the reservation and the project record in a single
`TransactWriteItems` call:

```text
TransactItems:
  [0] Put NAME#<nameKey> / RESERVATION      ConditionExpression: attribute_not_exists(PK)
  [1] Put PROJECT#<projectId> / META        ConditionExpression: attribute_not_exists(PK)
```

DynamoDB evaluates both conditions and applies both writes atomically, or applies neither. If the
reservation already exists, the whole transaction is cancelled with
`TransactionCanceledException` and no project record is written; a failed create leaves no
partial state (`tests/unit/test_repository.py::test_failed_create_leaves_no_partial_write`).
The second condition is defensive: `projectId` is a fresh UUID, so a collision is not expected,
but the condition turns a collision into an error rather than a silent overwrite.

### Mapping the cancellation to HTTP 409

The repository inspects `CancellationReasons` in the error response. Index 0 corresponds to the
reservation put; if its `Code` is `ConditionalCheckFailed` the repository raises the domain
exception `ProjectNameTakenError(name)`. Any other cancellation reason (throttling, a failed
project-record condition, a validation error) is re-raised unchanged and surfaces as a `500`.
Some client libraries and emulators omit `CancellationReasons` and only include the reason
text in the message, so as a fallback the repository also treats an empty reasons list whose
message contains `ConditionalCheckFailed` as a name conflict.

`api/errors.py` maps `ProjectNameTakenError` to a problem+json response:

```json
{
  "type": "https://projects-api.example/problems/project-name-taken",
  "title": "Project name already exists",
  "status": 409,
  "detail": "A project named 'My-First-Agent' already exists.",
  "instance": "/v1/projects"
}
```

The `409` reveals that a name exists somewhere in the system, including under another owner.
This is intentional and unavoidable for a globally unique namespace (a later hostname would
reveal the same fact); the project id and owner are not disclosed.

### Why not check uniqueness with a GSI

The obvious alternative is a GSI keyed on `nameKey` and a read-then-write: query the index, and
if nothing is found, put the project. This is wrong for two reasons:

1. **Race.** Two requests for the same name can both query, both see nothing, and both write.
   Nothing in DynamoDB stops the second put, so the system ends up with two projects sharing a
   name, and the future hostname mapping breaks. Conditional expressions cannot fix this because
   a condition can only reference the item being written, and neither project item is keyed by
   the name.
2. **Eventual consistency.** Global secondary indexes are eventually consistent; a project
   written milliseconds ago may not yet be visible in the index, widening the race window
   even for a single client retrying.

Putting the name in the primary key of a dedicated item converts the uniqueness rule into
something DynamoDB enforces with a strongly consistent conditional write, and the transaction
ties that guarantee to the project record. This is the pattern the repo's rule "always use
`ConditionExpression`s; never read-then-write" (`CLAUDE.md`) exists for.

### Releasing the reservation on delete

`ProjectRepository.delete(project_id, owner_id)` (behind `DELETE /v1/projects/{projectId}`)
first reads the record with a consistent `GetItem`: the reservation's key is `NAME#<nameKey>`,
and the name key is only known from the record. A missing record, or one owned by another key,
raises `ProjectNotFoundError` (`404`, never `403`) before anything is written. It then removes
both items in one `TransactWriteItems`:

```text
TransactItems:
  [0] Delete PROJECT#<projectId> / META   ConditionExpression: attribute_exists(PK) AND ownerId = :owner
  [1] Delete NAME#<nameKey> / RESERVATION ConditionExpression: projectId = :id
```

The read does not weaken the "never read-then-write" rule because the deletes are still
conditional: if the record vanished or changed owner between the read and the write (a race
with another delete), condition [0] fails and the request ends as `404` like any other missing
project. Condition [1] ensures the reservation is released only if it still points at the
project being deleted, so a stale request cannot free a name that has since been legitimately
re-reserved. If [1] fails while [0] would have passed, the record exists but its name is not
reserved for it; that is an invariant violation, so the repository logs both keys at error
level and lets the error surface as `500` rather than reporting success and leaving a dangling
reservation. Because both deletes are in one transaction, a name is either fully owned or fully
free; there is no window in which the record is gone but the name is still blocked, or vice
versa. After a successful delete, a create with the same name (any casing, any owner) succeeds
with `201` (`tests/unit/test_repository.py::test_delete_removes_record_and_reservation_and_frees_the_name`).

## Consequences

Positive:

- **Correct under concurrency.** Uniqueness is enforced by DynamoDB's primary key and a
  strongly consistent conditional write, not by application-level reads. Concurrent creates of
  the same name yield exactly one `201` and the rest `409`.
- **No orphaned state.** Create and delete are each a single transaction, so a project and its
  reservation always exist or vanish together. Tests assert this.
- **Explicit, testable rules.** `name_key` is a pure function with unit tests; the request
  model, the repository and any future hostname mapping all call the same code.
- **Cheap.** One extra small item per project and one transaction (2 write units, billed at
  twice the standard write cost) per create. There is no extra index to pay for or keep
  consistent.
- **Future-proof for hostnames.** The reservation item is the natural place to attach a
  hostname or certificate reference later, and the key format already reflects DNS
  case-insensitivity.

Negative:

- **Global namespace.** Early adopters can claim generic names (`api`, `test`) for all users.
  A reserved-word list or per-tenant prefixes may be needed before general availability.
- **Information disclosure.** A `409` confirms a name exists somewhere. Acceptable for a public
  hostname namespace; noted for the security review.
- **Renames are not supported.** Changing a name would require a transaction that deletes the
  old reservation, creates a new one and updates the record, with the new reservation
  conditioned on `attribute_not_exists`. Not in scope today.
- **Transactional writes cost and latency.** `TransactWriteItems` is roughly twice the write
  cost of a plain put and has slightly higher latency. At this service's volumes it is
  negligible.
- **Two normalisations to keep aligned.** The display normalisation (`normalise_name`) and the
  key normalisation (`name_key`) must evolve together; a change to either would require
  re-keying existing reservation items. The rules therefore live in one module, and a stricter
  hostname key, if introduced, should be added as a new item type rather than by changing
  `name_key`.

## When to revisit

- Provisioning (S4-403) defines the hostname mapping. If two distinct `name_key`s can map to the
  same hostname (for example `a b` and `a_b` both becoming `a-b`), a second reservation on the
  hostname key must be added to the create transaction.
- Names need to be scoped per organisation or tenant rather than globally; the key would become
  `NAME#<tenant>#<nameKey>`.
- A rename endpoint is requested.
- Squatting on desirable names becomes a problem and a reserved-word list, expiry for
  never-provisioned projects, or claim verification is needed.
