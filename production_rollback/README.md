# production_rollback/

Each rollback request lives at `production_rollback/{date}/rollback_approval.json`,
where `{date}` is the *current* date the rollback is being requested on
(not the target date being rolled back to -- that is the `target_date`
field inside the file).

This path is protected by `.github/CODEOWNERS` -- once Branch Protection's
"Require review from Code Owners" is enabled, changes here require
Director review via PR. AI/automation accounts must never set
`status: APPROVED` here directly.

See `scripts/rollback_latest.py` for the (currently inactive -- no
workflow trigger exists) execution logic, and
`docs/production/SPI_Production_Approval_Contract_v0.4.md` for the
full schema.
