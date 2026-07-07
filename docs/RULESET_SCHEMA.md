# Ruleset schema

Rulesets are YAML or JSON documents stored in S3 (referenced by `RULESET_URI`).

## Version 1

```yaml
version: "1"

default:
  drop_columns:
    - email
    - phone_number

# Optional: longest matching prefix wins
overrides:
  - prefix: datasets/events/
    drop_columns:
      - user_id
      - device_id

# Optional: limit which keys are processed (fnmatch globs on full S3 key)
include_globs:
  - "*.parquet"
  - "*.csv"
  - "*.csv.gz"
exclude_globs:
  - "_temporary/*"

csv:
  delimiter: ","
  quotechar: '"'
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `version` | yes | Must be `"1"` |
| `default.drop_columns` | yes | Columns to remove when no override matches |
| `overrides[].prefix` | no | S3 key prefix; longest match wins |
| `overrides[].drop_columns` | yes | Additional/explicit columns for that prefix |
| `include_globs` | no | If set, key must match at least one glob |
| `exclude_globs` | no | If any glob matches, object is skipped |
| `csv.delimiter` | no | Default `,` |
| `csv.quotechar` | no | Default `"` |

### Column drop semantics

- Column named in `drop_columns` but **absent** in file → **ignored** (success).
- Columns **not** listed → **kept**.
- Matching is **case-sensitive** (header names for CSV, field names for Parquet).

### Key mapping (Lambda env, not ruleset)

Default (recommended): write back to the **same bucket** at `sanitized/<full source key>`.

- `DEST_BUCKET`: same as the raw bucket.
- `SOURCE_PREFIX`: `""` (empty).
- `DEST_PREFIX`: `sanitized/`.

Example: source key `kohort-datalocker/t=installs/dt=2025-09-28/h=0/file.parquet` → dest key `sanitized/kohort-datalocker/t=installs/dt=2025-09-28/h=0/file.parquet`.

If `SOURCE_PREFIX` is non-empty, it is stripped before `DEST_PREFIX` is prepended (advanced; use only when you intend a different layout).
