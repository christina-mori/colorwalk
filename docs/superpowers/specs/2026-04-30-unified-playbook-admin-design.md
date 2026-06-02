# Unified Playbook Admin Design

Date: 2026-04-30
Project: ColorWalk Studio
Scope: Replace the current split Official / Community playbook presentation with a unified feed, and add an admin curation workflow that supports drag-and-drop ordering for both official and community items.

## Goal

Turn playbook management into one unified curation workflow:

- Frontend no longer separates `Official` and `Community`
- Frontend shows one mixed playbook feed
- Admin can review community submissions
- Admin can curate both official and community items in one shared pool
- Admin can drag cards to control the exact public display order

## Current State

There are currently two different playbook systems:

1. Official playbooks
   - Hardcoded in `static/js/main.js` as the `PLAYBOOK` constant
   - Always visible in the frontend
   - Not editable in admin

2. Community submissions
   - Stored in SQLite
   - Reviewed in `/admin`
   - Approved submissions appear in the frontend community tab
   - Ordering is controlled by numeric `sort_rank`

This split creates three product problems:

- The frontend experience is fragmented by source
- Official items cannot be curated from admin
- The current admin ordering UX is too manual for ongoing content operations

## Product Decision

Adopt a unified playbook content pool.

`official` and `community` remain meaningful as content origins, but they are no longer separate frontend sections. Once an item is published, it becomes a single public playbook card in one shared feed.

## User Experience

### Frontend

On `/app`:

- Remove the `Official` and `Community` source tabs
- Keep the mode filter tabs (`All`, `ColorWalk`, `Dot Puzzle`)
- Load playbooks from one unified feed endpoint
- Render all public items in one mixed grid
- Do not show source labels to end users

On the landing page:

- No immediate redesign is required in this phase
- Existing static landing galleries can remain for now
- The scope of this project is the `/app` playbook experience and admin curation workflow

### Admin

Replace the current single-purpose community moderation page with three clear views:

1. `Review`
   - Shows pending community submissions only
   - Admin can approve or reject
   - Approval publishes the item into the unified playbook pool

2. `Live Feed`
   - Shows the exact public order of all visible playbook items
   - Includes both official and approved community content
   - Supports drag-and-drop reordering
   - Uses explicit `Save order` and `Cancel` actions

3. `Library`
   - Shows all available playbook items regardless of whether they are currently visible
   - Includes official items and approved community items
   - Supports hide / show / inspect management actions

The admin UI may still display a small `Official` or `Community` badge for internal recognition, but the public feed should not expose source labels.

## Information Model

Separate submission records from public playbook items.

### Submission

Purpose:

- Preserve community intake and moderation history
- Track who submitted what and when
- Preserve raw params and moderation notes

Community submissions remain stored in the existing submissions table, with minimal behavior changes.

### Playbook Item

Purpose:

- Represent any item that can appear in the public playbook feed
- Control public title, image, mode, origin, visibility, and order

This new model becomes the source of truth for frontend playbook rendering.

Recommended fields:

- `id`
- `source_type`
  - `official`
  - `community`
- `source_ref_id`
  - official preset id or submission id
- `mode`
  - `dot`
  - `colorwalk`
- `label`
- `image_url` or media reference
- `settings_json`
- `is_visible`
- `sort_rank`
- `created_at`
- `updated_at`
- `published_at`

## Data Flow

### Official items

Official playbooks should be migrated out of the hardcoded frontend constant and stored as playbook items.

Migration behavior:

- Seed the existing 8 official examples into the new playbook item store
- Preserve their images and settings
- Mark them as `source_type = official`
- Assign initial feed order values

### Community items

Community submission flow remains:

- user submits
- item enters `pending`
- admin approves or rejects

New publish behavior on approval:

- approving a submission creates or updates a corresponding playbook item
- the playbook item is marked visible
- it receives a default sort rank at the end of the feed

Rejected items do not create public playbook items.

## Ordering Behavior

The public feed order is controlled only by playbook items.

Recommended UX rules:

- drag-and-drop is available only in the `Live Feed` view
- dragging is enabled only in explicit reorder mode
- multiple moves can be made before saving
- `Save order` writes the updated ranks in one batch
- `Cancel` restores the last saved order
- filtering and search can exist in browse mode, but reorder mode should operate on the full visible list only

Recommended persistence behavior:

- save contiguous order values in one transaction
- use a stable rank sequence like `100, 200, 300...` or rewrite to `1..N`
- do not depend on hand-edited numeric input once drag sorting exists

## API Changes

### Public feed

Replace the current split frontend loading approach with one unified public endpoint.

Recommended endpoint:

- `GET /api/playbooks`

Query support:

- optional `mode=all|dot|colorwalk`

Returns:

- all visible playbook items sorted by public order

This endpoint should replace the current frontend dependency on:

- hardcoded official `PLAYBOOK`
- `/api/community/list` for public community cards

### Admin

Recommended admin endpoints:

- `GET /api/admin/playbooks`
  - list unified playbook items
- `POST /api/admin/playbooks/reorder`
  - save drag-and-drop order in batch
- `POST /api/admin/playbooks/<id>/hide`
  - remove from public feed without deleting
- `POST /api/admin/playbooks/<id>/show`
  - restore to public feed

Existing endpoints for submission review can remain, but approval behavior should publish into the playbook item store.

## Frontend Refactor Scope

The frontend should move from hardcoded official presets to API-driven playbook items.

Required changes:

- remove source tab state from `static/js/main.js`
- replace `PLAYBOOK + communityItems` merge logic with a single fetched list
- preserve current preset-apply behavior
- continue supporting mode filtering on the client or server

Important compatibility rule:

- `settings_json` for `dot` items must continue to support the full schema described in `CLAUDE.md`
- legacy items missing fields must still be normalized with safe defaults

## Admin UX Details

### Review

Keep this simple:

- large preview image
- creator name
- description
- mode
- created time
- approve / reject

### Live Feed

Primary working screen for operators:

- one card grid or vertical card stack representing actual public order
- visible order numbers
- drag handle shown in reorder mode
- sticky top action bar in reorder mode:
  - `Save order`
  - `Cancel`
- quick actions per card:
  - `Hide`
  - `Open details`
  - optional `Move to top`
  - optional `Move to bottom`

### Library

Secondary management screen:

- browse all official and approved community items
- search by title / creator / id
- filter by mode, source, visibility
- show whether each item is live or hidden

## Migration Plan

Recommended rollout:

1. Create the new playbook item storage
2. Seed official playbooks into it
3. Backfill approved community submissions into it
4. Add admin unified feed views
5. Switch `/app` to read from unified public playbook endpoint
6. Remove public source tabs from the UI

## Error Handling

- If an official seeded item references a missing image, it should not crash the feed; admin should still be able to inspect it
- If reorder save fails, keep the old order and show a clear admin error
- If a community submission is approved but playbook publication fails, approval should not silently succeed; the operation must fail as one unit or clearly report partial failure

## Testing

Minimum validation after implementation:

1. `/app` loads one unified playbook feed with no source tabs
2. Mode filters still work for `All`, `ColorWalk`, `Dot Puzzle`
3. Official and approved community items both appear in the same feed
4. Pending submissions still appear in admin review
5. Approving a community submission publishes it into the unified feed
6. Dragging cards in admin changes public order after save
7. Cancel in reorder mode restores previous order
8. Hidden items disappear from the public feed but remain available in library
9. Existing official Dot Puzzle and ColorWalk items still apply correct settings when selected

## Out of Scope

This design does not include:

- full landing page redesign around the new feed
- multi-admin collaboration conflict handling
- scheduled publishing
- bulk import UI for official items
- analytics or performance dashboards

## Recommendation

Implement this as a unified content pool now rather than extending the current split system. The extra modeling work is justified because the product direction has already moved to:

- one mixed public feed
- no visible distinction between official and community
- admin-first curation and ordering

This avoids a short-term patch that would require a second rewrite later.
