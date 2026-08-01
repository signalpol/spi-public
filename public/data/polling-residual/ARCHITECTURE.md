# SPI Polling Residual Data Architecture — Public Summary

**Status:** Architecture approved; database implementation pending  
**Date:** 2026-08-01 KST

SPI uses three coordinated layers:

```text
Supabase   = operational normalized database
spi-spin   = private schema, ETL, validation, and research code
spi-public = approved public datasets and methodology
```

## Public repository role

This repository is not the live operational database. It receives only versioned artifacts that have passed validation and publication approval, including:

- district and regional polling-residual summaries;
- methodology and data dictionaries;
- source and release manifests;
- dashboard-ready JSON and GeoJSON;
- public residual heat maps and reports.

The following are excluded from public releases unless separately approved:

- provisional HVA coefficients;
- internal research notes;
- unresolved mapping or validation failures;
- unverified causal classifications;
- credentials and private database configuration.

## Data flow

```text
Official poll and election sources
        ↓
private collection and validation in spi-spin
        ↓
normalized operational storage in Supabase
        ↓
release validation and approval
        ↓
versioned public snapshots in spi-public
```

Every published dataset must include a release ID, schema version, generation timestamp, and source manifest.

The canonical architecture decision is maintained in `signalpol/spi-spin` under:

```text
docs/architecture/ADR-2026-08-01-polling-residual-data-platform.md
```
