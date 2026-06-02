# ColorWalk Studio Working Rules

## Project Scope

ColorWalk Studio is a small Flask app for two image effects:

- `ColorWalk`: photo + color block + text
- `Dot Puzzle`: photo + block + cutout dots / shapes / text

The app is currently single-repo, no database, no build step.

## Directory Conventions

- `app.py`
  - Flask routes and request parsing only.
  - Keep route handlers thin.
- `utils/`
  - Pure image-generation logic.
  - `colorwalk.py` and `dot_puzzle.py` should stay framework-light and testable.
- `templates/`
  - `index.html` is the app UI.
  - `landing.html` is the landing page.
- `static/js/main.js`
  - Frontend state and UI interactions live here.
  - Do not introduce a second JS entry without a strong reason.
- `static/css/style.css`
  - Shared app styling.
- `tests/`
  - Put Python regression tests here using `unittest` unless the repo later adopts another test runner.

## State Rules

- `manualDots` and `blockManualDots` must always use normalized coordinates (`0..1`).
- Preview canvas state must stay in sync after:
  - upload
  - crop
  - preset apply
  - decouple toggle
  - distribution switch
- Download/export must read current UI state, not stale cached params.
- When auto color is used in ColorWalk, preview and export should reuse the same extracted color value.

## Playbook Rules

- New or updated Dot Puzzle presets should prefer the full schema:
  - `dpPosition`
  - `dpBlockRatio`
  - `dpBlockType`
  - `dpColor1`
  - `dpGrad1`
  - `dpGrad2`
  - `dpStripe1`
  - `dpStripe2`
  - `dpGradDir`
  - `dpStripeDir`
  - `dpShape`
  - `dpCustomText`
  - `dpDotSize`
  - `dpDotCount`
  - `dpDistribution`
  - `dpBlockDistribution`
  - `dpSizeRandom`
  - `dpDecouple`
  - `dpText`
  - `dpTextSize`
  - `dpTextColor`
  - `dpSeed`
  - `dpManualPositions`
  - `dpBlockManualPositions`
- If older playbook entries omit fields, frontend normalization must backfill safe defaults.

## I18n Rules

- `/app` and `/` both need English + Chinese switching.
- Any new user-facing copy must be wired into both languages in the same change.
- Do not leave one-off hardcoded UI strings behind in templates if they are meant to switch language.

## Validation Baseline

Before closing a change that touches Dot Puzzle or Playbook, verify at least:

1. `/app` upload -> effect -> preview -> download
2. Stripe `vertical` / `horizontal`
3. Decouple on/off
4. Block distribution: `linked`, `random`, `grid`, `edge`, `manual`
5. Crop after manual points
6. Playbook -> upload -> apply -> edit -> export
7. English / Chinese switch on both app and landing page

## Editing Style

- Prefer small, local changes over broad rewrites.
- Keep image logic in Python, UI/state logic in `main.js`.
- Add short comments only where state or math is easy to misread.
