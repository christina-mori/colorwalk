# Community Submit Render Consistency Design

Date: 2026-04-30

## Goal

Make the image saved through community submission match the user's final downloaded image.

## Current Problem

The editor preview uses a downscaled preview image for responsiveness.
Download already compensates for that by scaling render-sensitive parameters like dot size and text size back up to the source image size.
Community submission does not reuse that scaling step, so the server renders a different result for admin/community cards.

## Decision

Keep preview rendering unchanged.
For community submission, generate the same final PNG used for download on the client and upload that finished image directly.
The backend should save that final image as-is, with rendering as a fallback only.

## Scope

- `static/js/main.js`
- `app.py`
- `tests/test_community_api.py`

## Non-Goals

- No changes to Python rendering logic.
- No changes to official playbooks.
- No visual redesign of admin/community cards.

## Validation

For the same edited work:

1. Main editor preview can stay lightweight and preview-oriented.
2. Downloaded output remains unchanged.
3. Submitted community/admin image should be byte-for-byte sourced from the same final PNG generation path as download.
