from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    request,
    send_file,
    session,
)
from PIL import Image

from utils.colorwalk import extract_dominant_color, make_colorwalk
from utils.community_store import (
    approve_submission,
    backfill_approved_submissions_to_playbook_items,
    count_recent_submissions,
    create_submission,
    ensure_playbook_seed,
    ensure_storage,
    fingerprint_exists,
    get_playbook_item_by_source,
    get_submission_by_filename,
    list_admin_playbook_items,
    list_admin_submissions,
    list_public_submissions,
    next_approved_rank,
    reject_submission,
    reorder_playbook_items,
    set_playbook_item_visibility,
    update_submission_rank,
)
from utils.dot_puzzle import make_dot_puzzle

UTC = timezone.utc
MAX_TEXT_LENGTH = 120
MAX_DISPLAY_NAME_LENGTH = 20
MIN_DISPLAY_NAME_LENGTH = 2
RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW_HOURS = 24

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_PATH, COMMUNITY_DIR = ensure_storage(DATA_DIR)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_COMMUNITY_SUBMISSION_MB", "20")) * 1024 * 1024
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "colorwalk-dev-secret")
app.config["ADMIN_PASSWORD"] = os.getenv("ADMIN_PASSWORD", "changeme-admin")
app.config["SUBMISSION_SALT"] = os.getenv("SUBMISSION_SALT", "colorwalk-dev-salt")
app.config["APP_BASE_URL"] = os.getenv("APP_BASE_URL", "")
app.config["DATA_DIR"] = str(DATA_DIR)
app.config["DB_PATH"] = str(DB_PATH)
app.config["COMMUNITY_DIR"] = str(COMMUNITY_DIR)


def _load_image(file_storage) -> Image.Image:
    with Image.open(file_storage.stream) as img:
        return img.convert("RGBA")


def _img_to_bytes(img: Image.Image, fmt: str = "PNG") -> io.BytesIO:
    buf = io.BytesIO()
    if fmt.upper() == "JPG":
        img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=92)
    else:
        img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _coerce_json_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return value
    return value


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return default


def _coerce_int(value, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _coerce_float(value, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _coerce_color_triplet(value, default=None):
    parsed = _coerce_json_value(value)
    if parsed is None:
        return default
    if isinstance(parsed, (list, tuple)):
        return tuple(parsed)
    return default


def _coerce_block_color(value, default):
    parsed = _coerce_json_value(value)
    if parsed is None:
        return default
    if isinstance(parsed, (list, tuple)) and parsed and isinstance(parsed[0], (list, tuple)):
        return [tuple(c) for c in parsed]
    if isinstance(parsed, (list, tuple)):
        return tuple(parsed)
    return default


def _make_dot_result(img: Image.Image, form_data) -> Image.Image:
    position = form_data.get("position", "right")
    block_ratio = _coerce_float(form_data.get("block_ratio", 0.4), 0.4)
    block_type = form_data.get("block_type", "solid")

    block_color = _coerce_block_color(form_data.get("block_color"), (200, 180, 160))

    shape = form_data.get("shape", "circle")
    custom_text = form_data.get("custom_text", "")
    dot_size = _coerce_int(form_data.get("dot_size", 60), 60)
    dot_count = _coerce_int(form_data.get("dot_count", 12), 12)
    distribution = form_data.get("distribution", "random")
    text_overlay = form_data.get("text_overlay", "")
    text_font_size = _coerce_int(form_data.get("text_font_size", 32), 32)
    text_color = _coerce_color_triplet(form_data.get("text_color"), None)
    gradient_dir = form_data.get("gradient_dir", "vertical")
    stripe_dir = form_data.get("stripe_dir", "vertical")
    size_random = _coerce_bool(form_data.get("size_random", False), False)
    decouple = _coerce_bool(form_data.get("decouple", False), False)
    seed_raw = form_data.get("seed")
    seed = _coerce_int(seed_raw, 0) if seed_raw not in (None, "") else None

    manual_positions = _coerce_json_value(form_data.get("manual_positions"))
    block_distribution = form_data.get("block_distribution")
    block_manual_positions = _coerce_json_value(form_data.get("block_manual_positions"))

    return make_dot_puzzle(
        img.convert("RGB"),
        position=position,
        block_ratio=block_ratio,
        block_type=block_type,
        block_color=block_color,
        shape=shape,
        custom_text=custom_text,
        dot_size=dot_size,
        dot_count=dot_count,
        distribution=distribution,
        manual_positions=manual_positions,
        text_overlay=text_overlay,
        text_font_size=text_font_size,
        text_color=text_color,
        gradient_dir=gradient_dir,
        stripe_dir=stripe_dir,
        size_random=size_random,
        decouple=decouple,
        seed=seed,
        block_distribution=block_distribution,
        block_manual_positions=block_manual_positions,
    )


def _make_colorwalk_result(img: Image.Image, form_data) -> Image.Image:
    color = _coerce_color_triplet(form_data.get("color"), None)
    color_ratio = _coerce_float(form_data.get("color_ratio", 0.45), 0.45)
    text = form_data.get("text", "")
    font_size = _coerce_int(form_data.get("font_size", 45), 45)
    text_color = _coerce_color_triplet(form_data.get("text_color"), None)
    return make_colorwalk(
        img.convert("RGB"),
        color=color,
        color_ratio=color_ratio,
        text=text,
        font_size=font_size,
        text_color=text_color,
    )


def _render_result_from_form(mode: str, img: Image.Image, form_data) -> Image.Image:
    if mode == "dot":
        return _make_dot_result(img, form_data)
    if mode == "colorwalk":
        return _make_colorwalk_result(img, form_data)
    raise ValueError("invalid mode")


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_mode(mode: str) -> str | None:
    return mode if mode in {"dot", "colorwalk"} else None


def _require_admin() -> bool:
    return session.get("is_admin") is True


def _hash_value(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _get_ip_hash() -> str:
    return _hash_value(f"{_get_client_ip()}:{app.config['SUBMISSION_SALT']}")


def _validate_submission_fields(display_name: str, description: str, mode: str) -> tuple[bool, str | None]:
    if not mode:
        return False, "Invalid mode."
    clean_name = display_name.strip()
    if len(clean_name) < MIN_DISPLAY_NAME_LENGTH or len(clean_name) > MAX_DISPLAY_NAME_LENGTH:
        return False, "Display name must be 2-20 characters."
    if len(description.strip()) > MAX_TEXT_LENGTH:
        return False, "Description must be 120 characters or fewer."
    return True, None


def _build_fingerprint(mode: str, params_json: str, image_bytes: bytes) -> str:
    payload = hashlib.sha256(image_bytes).hexdigest()
    return _hash_value(f"{mode}:{params_json}:{payload}")


def _recent_window_start() -> str:
    return (datetime.now(UTC) - timedelta(hours=RATE_LIMIT_WINDOW_HOURS)).isoformat()


def _image_url_from_path(image_path: str) -> str:
    if image_path.startswith("gallery/"):
        return f"/static/{image_path}"
    if image_path.startswith("community/"):
        return f"/media/community/{Path(image_path).name}"
    return image_path


def _label_for_mode(mode: str) -> str:
    return "Dot Puzzle" if mode == "dot" else "ColorWalk"


def _serialize_playbook_item(row: dict) -> dict:
    settings = json.loads(row["settings_json"])
    return {
        "id": row["id"],
        "mode": row["mode"],
        "display_name": row["display_name"],
        "description": row["description"],
        "image_url": _image_url_from_path(row["image_path"]),
        "image_width": row["image_width"],
        "image_height": row["image_height"],
        "sort_rank": row["sort_rank"],
        "settings": settings,
        "label": _label_for_mode(row["mode"]),
        "source_type": row["source_type"],
        "is_visible": bool(row["is_visible"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "published_at": row["published_at"],
        "source_ref_id": row["source_ref_id"],
    }


def _serialize_admin_submission(row: dict) -> dict:
    data = dict(row)
    data["settings"] = json.loads(row["params_json"])
    data["image_url"] = f"/media/community/{row['image_filename']}"
    del data["params_json"]
    return data


def _bootstrap_playbooks() -> None:
    now_iso = _utc_now_iso()
    ensure_playbook_seed(app.config["DB_PATH"], BASE_DIR, now_iso)
    backfill_approved_submissions_to_playbook_items(app.config["DB_PATH"])


_bootstrap_playbooks()


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/app")
def index():
    return render_template("index.html")


@app.route("/admin")
def admin():
    if _require_admin():
        return render_template("admin.html")
    return render_template("admin_login.html")


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/api/extract-color", methods=["POST"])
def api_extract_color():
    file = request.files.get("image")
    if not file:
        return _json_error("no image")
    with Image.open(file.stream) as source_img:
        img = source_img.convert("RGB")
    color = extract_dominant_color(img)
    return jsonify({"color": list(color)})


@app.route("/api/colorwalk", methods=["POST"])
def api_colorwalk():
    file = request.files.get("image")
    if not file:
        return _json_error("no image")

    fmt = request.form.get("format", "PNG").upper()
    with Image.open(file.stream) as source_img:
        img = source_img.convert("RGB")
    result = _make_colorwalk_result(img, request.form)

    mimetype = "image/png" if fmt == "PNG" else "image/jpeg"
    suffix = "png" if fmt == "PNG" else "jpg"
    return send_file(
        _img_to_bytes(result, fmt),
        mimetype=mimetype,
        download_name=f"colorwalk.{suffix}",
        as_attachment=False,
    )


@app.route("/api/dot-puzzle", methods=["POST"])
def api_dot_puzzle():
    file = request.files.get("image")
    if not file:
        return _json_error("no image")

    fmt = request.form.get("format", "PNG").upper()
    with Image.open(file.stream) as source_img:
        img = source_img.convert("RGB")
    result = _make_dot_result(img, request.form)

    mimetype = "image/png" if fmt == "PNG" else "image/jpeg"
    suffix = "png" if fmt == "PNG" else "jpg"
    return send_file(
        _img_to_bytes(result, fmt),
        mimetype=mimetype,
        download_name=f"dot_puzzle.{suffix}",
        as_attachment=False,
    )


@app.route("/api/playbooks")
def api_playbooks():
    mode = request.args.get("mode", "all")
    rows = list_public_submissions(app.config["DB_PATH"], mode)
    return jsonify({"items": [_serialize_playbook_item(row) for row in rows]})


@app.route("/api/community/list")
def api_community_list():
    mode = request.args.get("mode", "all")
    rows = list_admin_playbook_items(
        app.config["DB_PATH"],
        visible_only=True,
        source_type="community",
        mode=mode,
    )
    return jsonify({"items": [_serialize_playbook_item(row) for row in rows]})


@app.route("/api/community/submit", methods=["POST"])
def api_community_submit():
    if request.form.get("website", "").strip():
        return _json_error("Submission rejected.", 400)

    file = request.files.get("image")
    rendered_file = request.files.get("rendered_image")
    if not file and not rendered_file:
        return _json_error("Image is required.")

    mode = _normalize_mode(request.form.get("mode", ""))
    display_name = request.form.get("display_name", "")
    description = request.form.get("description", "")
    valid, error = _validate_submission_fields(display_name, description, mode or "")
    if not valid:
        return _json_error(error or "Invalid submission.")

    params_json = request.form.get("params_json", "")
    if not params_json:
        return _json_error("Missing params.")

    try:
        params = json.loads(params_json)
    except json.JSONDecodeError:
        return _json_error("Invalid params JSON.")
    params_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))

    ip_hash = _get_ip_hash()
    recent_count = count_recent_submissions(app.config["DB_PATH"], ip_hash, _recent_window_start())
    if recent_count >= RATE_LIMIT_COUNT:
        return _json_error("Too many submissions. Please try again later.", 429)

    original_bytes = file.read() if file else b""
    rendered_bytes = rendered_file.read() if rendered_file else b""
    if not original_bytes and not rendered_bytes:
        return _json_error("Image is empty.")

    fingerprint_source = rendered_bytes or original_bytes
    fingerprint = _build_fingerprint(mode, params_json, fingerprint_source)
    if fingerprint_exists(app.config["DB_PATH"], fingerprint):
        return _json_error("This work has already been submitted.", 409)

    if rendered_bytes:
        try:
            with Image.open(io.BytesIO(rendered_bytes)) as rendered_img:
                rendered = rendered_img.convert("RGB")
        except Exception:
            return _json_error("Invalid rendered image.")
    else:
        with Image.open(io.BytesIO(original_bytes)) as source_img:
            img = source_img.convert("RGB")
        try:
            rendered = _render_result_from_form(mode, img, params)
        except Exception:
            return _json_error("Unable to render submission.")

    submission_id = uuid.uuid4().hex
    filename = f"{submission_id}.png"
    image_path = COMMUNITY_DIR / filename
    rendered.save(image_path, format="PNG")

    record = {
        "id": submission_id,
        "status": "pending",
        "display_name": display_name.strip(),
        "description": description.strip(),
        "mode": mode,
        "params_json": params_json,
        "image_filename": filename,
        "image_width": rendered.width,
        "image_height": rendered.height,
        "fingerprint": fingerprint,
        "ip_hash": ip_hash,
        "sort_rank": None,
        "review_note": "",
        "created_at": _utc_now_iso(),
        "reviewed_at": None,
    }
    row = create_submission(app.config["DB_PATH"], record)
    return jsonify({
        "message": "Submitted for review.",
        "item": _serialize_admin_submission(row),
    })


@app.route("/media/community/<path:filename>")
def media_community(filename: str):
    record = get_submission_by_filename(app.config["DB_PATH"], filename)
    if record is None:
        abort(404)
    if not _require_admin():
        linked = get_playbook_item_by_source(app.config["DB_PATH"], "community", record["id"])
        if record["status"] != "approved" or linked is None or not bool(linked["is_visible"]):
            abort(404)
    image_path = COMMUNITY_DIR / filename
    if not image_path.exists():
        abort(404)
    return send_file(image_path)


@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password", "")
    if password != app.config["ADMIN_PASSWORD"]:
        return render_template("admin_login.html", error="Invalid password."), 401
    session["is_admin"] = True
    return render_template("admin.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return render_template("admin_login.html")


@app.route("/api/admin/submissions")
def api_admin_submissions():
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    status = request.args.get("status", "pending")
    if status not in {"pending", "approved", "rejected"}:
        return _json_error("Invalid status.")
    rows = list_admin_submissions(app.config["DB_PATH"], status)
    return jsonify({"items": [_serialize_admin_submission(row) for row in rows]})


@app.route("/api/admin/submissions/<submission_id>/approve", methods=["POST"])
def api_admin_approve_submission(submission_id: str):
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    row = approve_submission(
        app.config["DB_PATH"],
        submission_id,
        _utc_now_iso(),
        next_approved_rank(app.config["DB_PATH"]),
    )
    if row is None:
        return _json_error("Submission not found.", 404)
    return jsonify({"item": _serialize_admin_submission(row)})


@app.route("/api/admin/submissions/<submission_id>/reject", methods=["POST"])
def api_admin_reject_submission(submission_id: str):
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    payload = request.get_json(silent=True) or {}
    review_note = str(payload.get("review_note", "")).strip()[:240]
    row = reject_submission(app.config["DB_PATH"], submission_id, _utc_now_iso(), review_note)
    if row is None:
        return _json_error("Submission not found.", 404)
    return jsonify({"item": _serialize_admin_submission(row)})


@app.route("/api/admin/submissions/<submission_id>/rank", methods=["POST"])
def api_admin_rank_submission(submission_id: str):
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    payload = request.get_json(silent=True) or {}
    try:
        sort_rank = int(payload.get("sort_rank"))
    except (TypeError, ValueError):
        return _json_error("Invalid sort rank.")
    row = update_submission_rank(app.config["DB_PATH"], submission_id, sort_rank)
    if row is None:
        return _json_error("Submission not found.", 404)
    return jsonify({"item": _serialize_admin_submission(row)})


@app.route("/api/admin/playbooks")
def api_admin_playbooks():
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    view = request.args.get("view", "live")
    visibility = request.args.get("visibility", "all")
    source = request.args.get("source", "all")
    mode = request.args.get("mode", "all")
    query = request.args.get("q", "").strip().lower()

    visible_only = True if view == "live" else None
    if view == "library":
        if visibility == "visible":
            visible_only = True
        elif visibility == "hidden":
            visible_only = False

    rows = list_admin_playbook_items(
        app.config["DB_PATH"],
        visible_only=visible_only,
        source_type=source,
        mode=mode,
    )
    items = [_serialize_playbook_item(row) for row in rows]
    if query:
        items = [
            item for item in items
            if query in item["id"].lower()
            or query in item["display_name"].lower()
            or query in item["description"].lower()
            or query in item["source_ref_id"].lower()
        ]
    return jsonify({"items": items})


@app.route("/api/admin/playbooks/reorder", methods=["POST"])
def api_admin_playbooks_reorder():
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    payload = request.get_json(silent=True) or {}
    item_ids = payload.get("item_ids")
    if not isinstance(item_ids, list) or not all(isinstance(item_id, str) for item_id in item_ids):
        return _json_error("Invalid item order.")
    rows = reorder_playbook_items(app.config["DB_PATH"], item_ids, _utc_now_iso())
    return jsonify({"items": [_serialize_playbook_item(row) for row in rows]})


@app.route("/api/admin/playbooks/<item_id>/hide", methods=["POST"])
def api_admin_hide_playbook(item_id: str):
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    row = set_playbook_item_visibility(app.config["DB_PATH"], item_id, False, _utc_now_iso())
    if row is None:
        return _json_error("Playbook not found.", 404)
    return jsonify({"item": _serialize_playbook_item(row)})


@app.route("/api/admin/playbooks/<item_id>/show", methods=["POST"])
def api_admin_show_playbook(item_id: str):
    if not _require_admin():
        return _json_error("Unauthorized.", 401)
    row = set_playbook_item_visibility(app.config["DB_PATH"], item_id, True, _utc_now_iso())
    if row is None:
        return _json_error("Playbook not found.", 404)
    return jsonify({"item": _serialize_playbook_item(row)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
