from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from utils.official_playbooks import build_official_playbook_records


SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL,
    params_json TEXT NOT NULL,
    image_filename TEXT NOT NULL,
    image_width INTEGER NOT NULL,
    image_height INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    sort_rank INTEGER,
    review_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_submissions_status
ON submissions(status);

CREATE INDEX IF NOT EXISTS idx_submissions_created_at
ON submissions(created_at);

CREATE INDEX IF NOT EXISTS idx_submissions_ip_hash
ON submissions(ip_hash);

CREATE INDEX IF NOT EXISTS idx_submissions_fingerprint
ON submissions(fingerprint);

CREATE TABLE IF NOT EXISTS playbook_items (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    settings_json TEXT NOT NULL,
    image_path TEXT NOT NULL,
    image_width INTEGER NOT NULL DEFAULT 0,
    image_height INTEGER NOT NULL DEFAULT 0,
    is_visible INTEGER NOT NULL DEFAULT 1,
    sort_rank INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_source
ON playbook_items(source_type, source_ref_id);

CREATE INDEX IF NOT EXISTS idx_playbook_visible_rank
ON playbook_items(is_visible, sort_rank);

CREATE INDEX IF NOT EXISTS idx_playbook_mode
ON playbook_items(mode);
"""


def _safe_json_loads(raw: str):
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def _rgb_array_to_hex(arr, fallback: str = "#FFFFFF") -> str:
    if isinstance(arr, (list, tuple)) and len(arr) >= 3:
        try:
            return "#" + "".join(f"{max(0, min(255, int(v))):02X}" for v in arr[:3])
        except (TypeError, ValueError):
            return fallback
    return fallback


def source_params_to_preset_settings(mode: str, params) -> dict:
    params = params or {}
    if mode == "colorwalk":
        ratio = params.get("color_ratio", 0.45)
        try:
            ratio_pct = round((float(ratio) or 0.45) * 100)
        except (TypeError, ValueError):
            ratio_pct = 45
        color_value = _safe_json_loads(params.get("color")) if isinstance(params.get("color"), str) else params.get("color")
        text_color_value = _safe_json_loads(params.get("text_color")) if isinstance(params.get("text_color"), str) else params.get("text_color")
        return {
            "cwRatio": ratio_pct,
            "cwAutoColor": color_value is None,
            "cwColor": _rgb_array_to_hex(color_value) if color_value is not None else None,
            "cwText": params.get("text", "") or "",
            "cwFontSize": int(params.get("font_size", 45) or 45),
            "cwAutoTextColor": text_color_value is None,
            "cwTextColor": _rgb_array_to_hex(text_color_value) if text_color_value is not None else None,
        }

    def parse_value(name, default=None):
        value = params.get(name, default)
        return _safe_json_loads(value) if isinstance(value, str) else value

    block_color = parse_value("block_color")
    manual_positions = parse_value("manual_positions")
    block_manual_positions = parse_value("block_manual_positions")
    text_color = parse_value("text_color")
    gradient_colors = block_color if isinstance(block_color, list) and block_color and isinstance(block_color[0], (list, tuple)) else None
    solid_color = block_color if isinstance(block_color, (list, tuple)) and block_color and not isinstance(block_color[0], (list, tuple)) else None
    try:
        ratio_pct = round((float(params.get("block_ratio", 0.4)) or 0.4) * 100)
    except (TypeError, ValueError):
        ratio_pct = 40
    return {
        "dpPosition": params.get("position", "right") or "right",
        "dpBlockRatio": ratio_pct,
        "dpBlockType": params.get("block_type", "solid") or "solid",
        "dpColor1": _rgb_array_to_hex(solid_color, "#C8B4A0"),
        "dpGrad1": _rgb_array_to_hex(gradient_colors[0], "#F5D0A9") if gradient_colors and len(gradient_colors) > 0 else "#F5D0A9",
        "dpGrad2": _rgb_array_to_hex(gradient_colors[1], "#9FC8E0") if gradient_colors and len(gradient_colors) > 1 else "#9FC8E0",
        "dpStripe1": _rgb_array_to_hex(gradient_colors[0], "#F5C0CC") if gradient_colors and len(gradient_colors) > 0 else "#F5C0CC",
        "dpStripe2": _rgb_array_to_hex(gradient_colors[1], "#A8C8E8") if gradient_colors and len(gradient_colors) > 1 else "#A8C8E8",
        "dpGradDir": params.get("gradient_dir", "vertical") or "vertical",
        "dpStripeDir": params.get("stripe_dir", "vertical") or "vertical",
        "dpShape": params.get("shape", "circle") or "circle",
        "dpCustomText": params.get("custom_text", "") or "",
        "dpDotSize": int(params.get("dot_size", 60) or 60),
        "dpDotCount": int(params.get("dot_count", 12) or 12),
        "dpDistribution": params.get("distribution", "random") or "random",
        "dpBlockDistribution": params.get("block_distribution", "linked") or "linked",
        "dpSizeRandom": str(params.get("size_random", "")).strip().lower() == "true" if not isinstance(params.get("size_random"), bool) else bool(params.get("size_random")),
        "dpDecouple": str(params.get("decouple", "")).strip().lower() == "true" if not isinstance(params.get("decouple"), bool) else bool(params.get("decouple")),
        "dpText": params.get("text_overlay", "") or "",
        "dpTextSize": int(params.get("text_font_size", 32) or 32),
        "dpTextColor": _rgb_array_to_hex(text_color, "#FFFFFF"),
        "dpSeed": int(params["seed"]) if params.get("seed") not in (None, "") else None,
        "dpManualPositions": manual_positions if isinstance(manual_positions, list) else None,
        "dpBlockManualPositions": block_manual_positions if isinstance(block_manual_positions, list) else None,
    }


def ensure_storage(data_dir: str | Path) -> tuple[Path, Path]:
    base = Path(data_dir)
    community_dir = base / "community"
    base.mkdir(parents=True, exist_ok=True)
    if not community_dir.exists():
        try:
            community_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            if not community_dir.exists():
                raise
    db_path = base / "colorwalk.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path, community_dir


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


@contextmanager
def managed_connection(db_path: str | Path):
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def create_submission(db_path: str | Path, record: dict) -> dict:
    with managed_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO submissions (
                id, status, display_name, description, mode, params_json,
                image_filename, image_width, image_height, fingerprint, ip_hash,
                sort_rank, review_note, created_at, reviewed_at
            ) VALUES (
                :id, :status, :display_name, :description, :mode, :params_json,
                :image_filename, :image_width, :image_height, :fingerprint, :ip_hash,
                :sort_rank, :review_note, :created_at, :reviewed_at
            )
            """,
            record,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ?",
            (record["id"],),
        ).fetchone()
    return row_to_dict(row)


def get_submission(db_path: str | Path, submission_id: str) -> dict | None:
    with managed_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
    return row_to_dict(row)


def get_submission_by_filename(db_path: str | Path, image_filename: str) -> dict | None:
    with managed_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM submissions WHERE image_filename = ?",
            (image_filename,),
        ).fetchone()
    return row_to_dict(row)


def get_playbook_item(db_path: str | Path, item_id: str) -> dict | None:
    with managed_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM playbook_items WHERE id = ?",
            (item_id,),
        ).fetchone()
    return row_to_dict(row)


def get_playbook_item_by_source(db_path: str | Path, source_type: str, source_ref_id: str) -> dict | None:
    with managed_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM playbook_items
            WHERE source_type = ? AND source_ref_id = ?
            """,
            (source_type, source_ref_id),
        ).fetchone()
    return row_to_dict(row)


def fingerprint_exists(db_path: str | Path, fingerprint: str) -> bool:
    with managed_connection(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM submissions WHERE fingerprint = ? LIMIT 1",
            (fingerprint,),
        ).fetchone()
    return row is not None


def count_recent_submissions(db_path: str | Path, ip_hash: str, created_after: str) -> int:
    with managed_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM submissions
            WHERE ip_hash = ? AND created_at >= ?
            """,
            (ip_hash, created_after),
        ).fetchone()
    return int(row["count"]) if row else 0


def _insert_playbook_item(conn: sqlite3.Connection, record: dict) -> None:
    conn.execute(
        """
        INSERT INTO playbook_items (
            id, source_type, source_ref_id, mode, display_name, description,
            settings_json, image_path, image_width, image_height, is_visible,
            sort_rank, created_at, updated_at, published_at
        ) VALUES (
            :id, :source_type, :source_ref_id, :mode, :display_name, :description,
            :settings_json, :image_path, :image_width, :image_height, :is_visible,
            :sort_rank, :created_at, :updated_at, :published_at
        )
        ON CONFLICT(id) DO UPDATE SET
            source_type = excluded.source_type,
            source_ref_id = excluded.source_ref_id,
            mode = excluded.mode,
            display_name = excluded.display_name,
            description = excluded.description,
            settings_json = excluded.settings_json,
            image_path = excluded.image_path,
            image_width = excluded.image_width,
            image_height = excluded.image_height,
            is_visible = excluded.is_visible,
            sort_rank = excluded.sort_rank,
            updated_at = excluded.updated_at,
            published_at = excluded.published_at
        """,
        record,
    )


def ensure_playbook_seed(db_path: str | Path, base_dir: str | Path, now_iso: str) -> None:
    records = build_official_playbook_records(base_dir, now_iso)
    with managed_connection(db_path) as conn:
        for record in records:
            _insert_playbook_item(conn, record)
        conn.commit()


def backfill_approved_submissions_to_playbook_items(db_path: str | Path) -> None:
    with managed_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM submissions
            WHERE status = 'approved'
            ORDER BY
                CASE WHEN sort_rank IS NULL THEN 1 ELSE 0 END ASC,
                sort_rank ASC,
                reviewed_at DESC,
                created_at DESC
            """
        ).fetchall()
        base_rank = 1000
        for index, row in enumerate(rows, start=1):
            row_dict = dict(row)
            existing = conn.execute(
                """
                SELECT id, sort_rank
                FROM playbook_items
                WHERE source_type = 'community' AND source_ref_id = ?
                """,
                (row_dict["id"],),
            ).fetchone()
            params = _safe_json_loads(row_dict["params_json"]) or {}
            sort_rank = row_dict["sort_rank"] if row_dict["sort_rank"] is not None else base_rank + index * 100
            record = {
                "id": existing["id"] if existing else f"community:{row_dict['id']}",
                "source_type": "community",
                "source_ref_id": row_dict["id"],
                "mode": row_dict["mode"],
                "display_name": row_dict["display_name"],
                "description": row_dict["description"],
                "settings_json": json.dumps(source_params_to_preset_settings(row_dict["mode"], params), ensure_ascii=False, separators=(",", ":")),
                "image_path": f"community/{row_dict['image_filename']}",
                "image_width": row_dict["image_width"],
                "image_height": row_dict["image_height"],
                "is_visible": 1,
                "sort_rank": existing["sort_rank"] if existing and existing["sort_rank"] is not None else sort_rank,
                "created_at": row_dict["created_at"],
                "updated_at": row_dict["reviewed_at"] or row_dict["created_at"],
                "published_at": row_dict["reviewed_at"] or row_dict["created_at"],
            }
            _insert_playbook_item(conn, record)
        conn.commit()


def list_public_submissions(db_path: str | Path, mode: str = "all") -> list[dict]:
    params: list[object] = [1]
    where_mode = ""
    if mode in {"dot", "colorwalk"}:
        where_mode = " AND mode = ?"
        params.append(mode)
    query = f"""
        SELECT *
        FROM playbook_items
        WHERE is_visible = ?{where_mode}
        ORDER BY sort_rank ASC, published_at ASC, created_at ASC
    """
    with managed_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


def list_admin_submissions(db_path: str | Path, status: str) -> list[dict]:
    if status == "approved":
        order_clause = """
            ORDER BY
                CASE WHEN sort_rank IS NULL THEN 1 ELSE 0 END ASC,
                sort_rank ASC,
                reviewed_at DESC,
                created_at DESC
        """
    elif status == "rejected":
        order_clause = "ORDER BY reviewed_at DESC, created_at DESC"
    else:
        order_clause = "ORDER BY created_at DESC"

    query = f"""
        SELECT *
        FROM submissions
        WHERE status = ?
        {order_clause}
    """
    with managed_connection(db_path) as conn:
        rows = conn.execute(query, (status,)).fetchall()
    return [row_to_dict(row) for row in rows]


def list_admin_playbook_items(
    db_path: str | Path,
    *,
    visible_only: bool | None = None,
    source_type: str = "all",
    mode: str = "all",
) -> list[dict]:
    conditions = []
    params: list[object] = []
    if visible_only is True:
        conditions.append("is_visible = 1")
    elif visible_only is False:
        conditions.append("is_visible = 0")
    if source_type in {"official", "community"}:
        conditions.append("source_type = ?")
        params.append(source_type)
    if mode in {"dot", "colorwalk"}:
        conditions.append("mode = ?")
        params.append(mode)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT *
        FROM playbook_items
        {where_clause}
        ORDER BY sort_rank ASC, published_at ASC, created_at ASC
    """
    with managed_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [row_to_dict(row) for row in rows]


def next_approved_rank(db_path: str | Path) -> int:
    with managed_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_rank), 0) AS max_rank FROM playbook_items WHERE is_visible = 1"
        ).fetchone()
    return int(row["max_rank"] or 0) + 100


def approve_submission(db_path: str | Path, submission_id: str, reviewed_at: str, default_rank: int) -> dict | None:
    with managed_connection(db_path) as conn:
        current = conn.execute(
            "SELECT * FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if current is None:
            return None
        row_dict = dict(current)
        sort_rank = row_dict["sort_rank"] if row_dict["sort_rank"] is not None else default_rank
        conn.execute(
            """
            UPDATE submissions
            SET status = 'approved', reviewed_at = ?, sort_rank = ?
            WHERE id = ?
            """,
            (reviewed_at, sort_rank, submission_id),
        )
        record = {
            "id": f"community:{submission_id}",
            "source_type": "community",
            "source_ref_id": submission_id,
            "mode": row_dict["mode"],
            "display_name": row_dict["display_name"],
            "description": row_dict["description"],
            "settings_json": json.dumps(
                source_params_to_preset_settings(row_dict["mode"], _safe_json_loads(row_dict["params_json"]) or {}),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "image_path": f"community/{row_dict['image_filename']}",
            "image_width": row_dict["image_width"],
            "image_height": row_dict["image_height"],
            "is_visible": 1,
            "sort_rank": sort_rank,
            "created_at": row_dict["created_at"],
            "updated_at": reviewed_at,
            "published_at": reviewed_at,
        }
        _insert_playbook_item(conn, record)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
    return row_to_dict(row)


def reject_submission(db_path: str | Path, submission_id: str, reviewed_at: str, review_note: str) -> dict | None:
    with managed_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE submissions
            SET status = 'rejected', reviewed_at = ?, review_note = ?
            WHERE id = ?
            """,
            (reviewed_at, review_note, submission_id),
        )
        conn.execute(
            """
            UPDATE playbook_items
            SET is_visible = 0, updated_at = ?
            WHERE source_type = 'community' AND source_ref_id = ?
            """,
            (reviewed_at, submission_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
    return row_to_dict(row)


def update_submission_rank(db_path: str | Path, submission_id: str, sort_rank: int) -> dict | None:
    with managed_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE submissions
            SET sort_rank = ?
            WHERE id = ? AND status = 'approved'
            """,
            (sort_rank, submission_id),
        )
        conn.execute(
            """
            UPDATE playbook_items
            SET sort_rank = ?, updated_at = COALESCE(published_at, created_at)
            WHERE source_type = 'community' AND source_ref_id = ?
            """,
            (sort_rank, submission_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
    return row_to_dict(row)


def reorder_playbook_items(db_path: str | Path, item_ids: list[str], updated_at: str) -> list[dict]:
    with managed_connection(db_path) as conn:
        for index, item_id in enumerate(item_ids, start=1):
            conn.execute(
                """
                UPDATE playbook_items
                SET sort_rank = ?, updated_at = ?
                WHERE id = ?
                """,
                (index * 100, updated_at, item_id),
            )
        conn.commit()
        placeholders = ",".join("?" for _ in item_ids)
        rows = conn.execute(
            f"SELECT * FROM playbook_items WHERE id IN ({placeholders}) ORDER BY sort_rank ASC",
            item_ids,
        ).fetchall() if item_ids else []
    return [row_to_dict(row) for row in rows]


def set_playbook_item_visibility(db_path: str | Path, item_id: str, is_visible: bool, updated_at: str) -> dict | None:
    with managed_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE playbook_items
            SET is_visible = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if is_visible else 0, updated_at, item_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM playbook_items WHERE id = ?",
            (item_id,),
        ).fetchone()
    return row_to_dict(row)
