# Incoming Publication Staging

This directory is the controlled handoff point for **SPI Auto Publisher v1.0**.

A publication run starts only when both conditions are met:

1. `incoming/manifest.json` exists and contains `"approved": true`.
2. Every file named in the manifest exists under `incoming/publication/`.

The publisher validates the package, archives it by date, verifies SHA-256 integrity, updates `reports/archive-index.json` and `reports/latest.json`, and then removes the processed staging package.

## Required package

```text
incoming/
├── manifest.json
└── publication/
    ├── morning-KR.md
    ├── morning-EN.md
    ├── election-KR.png
    ├── election-EN.png
    ├── conflicts-KR.png
    ├── conflicts-EN.png
    ├── signals-KR.png
    └── signals-EN.png
```

Use `manifest.example.json` as the template. Do not rename public archive folders or bypass the approval field.
