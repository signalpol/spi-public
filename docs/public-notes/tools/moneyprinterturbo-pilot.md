# MoneyPrinterTurbo — SPI / Leo Show Pilot Candidate

- Recorded: 2026-08-28
- Upstream: harry0703/MoneyPrinterTurbo
- Upstream URL: https://github.com/harry0703/MoneyPrinterTurbo
- Upstream license: MIT (verify again before production deployment)
- SPI status: PILOT CANDIDATE — NOT CORE

## Intended role

MoneyPrinterTurbo is retained as a candidate **SPI Video Production Engine** and a first-tier candidate for the **Leo Show Production Engine**.

It must remain an output/production layer. It does not replace or modify SPI analytical engines such as SEFM, SICAM, HIPM, HISM, BCVM, HFGM, or HAPM.

## Candidate workflow

SPI analysis/report
→ Leo Show script/commentary
→ MoneyPrinterTurbo video assembly
→ optional Leo avatar/lip-sync layer
→ 16:9 main program / 9:16 Shorts
→ distribution

## Relevant capabilities

- Script-to-video workflow
- Custom scripts
- Local media assets
- Stock footage sources
- TTS and subtitles
- Background music
- 16:9 and 9:16 output
- Batch generation
- WebUI / API / CLI / Agent workflows
- Potential social publishing workflow

## Pilot gate

Do not promote this project to SPI core infrastructure until a real Leo Show prototype is produced and evaluated.

Recommended PoC:
1. Use one completed SPI Morning Intelligence Briefing.
2. Produce a 3–5 minute Korean Leo Show prototype.
3. Reuse SPI dashboards/charts as local assets where appropriate.
4. Produce a 16:9 main video and a 9:16 short-form derivative.
5. Evaluate factual fidelity, visual quality, Korean TTS quality, subtitle accuracy, production time, automation rate, and operating cost.

## Adoption rule

- ADOPT: output is publication-ready or requires only light human editing.
- MODIFY: useful pipeline but requires a bounded adapter or avatar layer.
- REJECT: substantial manual editing remains or quality is below SPI publication standard.

## Safety / rights boundary

Do not use bundled/default music or external assets commercially without confirming usage rights. SPI production should prefer SPI-owned assets and separately licensed music/media. Never store API keys or credentials in this public repository.

## Preservation rationale

Unlike prompt/skill collections that duplicate existing SPI infrastructure, MoneyPrinterTurbo fills a distinct production/distribution-layer role. Preserve the reference for later Leo Show experimentation without installing it into SPI core at this stage.
