import importlib
import io
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

from PIL import Image
import utils.community_store as community_store


class CommunityApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path.cwd() / "tests" / ".tmp-appdata"
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATA_DIR"] = str(self.temp_dir)
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["ADMIN_PASSWORD"] = "admin-pass"
        os.environ["SUBMISSION_SALT"] = "salt-pass"
        sys.modules.pop("app", None)
        importlib.reload(community_store)
        import app as app_module  # import after env vars
        app_module = importlib.reload(app_module)
        app = app_module.app

        self.app = app
        self.app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def make_image_bytes(self, color=(220, 170, 150), size=(120, 90)):
        img = Image.new("RGB", size, color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def make_png_bytes(self, color=(220, 170, 150), size=(120, 90)):
        return self.make_image_bytes(color=color, size=size)

    def submit_payload(self, mode="colorwalk", color=(220, 170, 150), display_name="Test User", description="Short note"):
        if mode == "dot":
            params = {
                "position": "right",
                "block_ratio": 0.4,
                "block_type": "solid",
                "block_color": "[200,180,160]",
                "shape": "circle",
                "dot_size": "60",
                "dot_count": "12",
                "distribution": "random",
                "text_overlay": "",
                "text_font_size": "32",
                "text_color": "[255,255,255]",
                "format": "PNG",
            }
        else:
            params = {
                "color": "[12,34,56]",
                "color_ratio": 0.45,
                "text": "Hello",
                "font_size": 36,
                "format": "PNG",
            }
        return {
            "image": (self.make_image_bytes(color=color), "test.png"),
            "mode": mode,
            "display_name": display_name,
            "description": description,
            "website": "",
            "params_json": json.dumps(params),
        }

    def admin_login(self):
        return self.client.post("/admin/login", data={"password": "admin-pass"})

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_data(as_text=True), "ok")

    def test_official_seed_appears_in_unified_playbooks(self):
        public_items = self.client.get("/api/playbooks?mode=all").get_json()["items"]
        self.assertGreaterEqual(len(public_items), 8)
        self.assertTrue(any(item["source_type"] == "official" for item in public_items))
        self.assertTrue(any(item["mode"] == "dot" for item in public_items))
        self.assertTrue(any(item["mode"] == "colorwalk" for item in public_items))

    def test_submit_then_approve_then_unified_public_list(self):
        submit = self.client.post(
            "/api/community/submit",
            data=self.submit_payload("colorwalk", color=(220, 170, 150)),
            content_type="multipart/form-data",
        )
        self.assertEqual(submit.status_code, 200)
        item = submit.get_json()["item"]
        submission_id = item["id"]
        image_url = item["image_url"]

        public_before = self.client.get("/api/playbooks?mode=all").get_json()["items"]
        self.assertFalse(any(entry["source_type"] == "community" and entry["source_ref_id"] == submission_id for entry in public_before))

        hidden_media = self.client.get(image_url)
        self.assertEqual(hidden_media.status_code, 404)

        self.admin_login()
        approve = self.client.post(f"/api/admin/submissions/{submission_id}/approve")
        self.assertEqual(approve.status_code, 200)

        public_after = self.client.get("/api/playbooks?mode=all").get_json()["items"]
        approved_items = [entry for entry in public_after if entry["source_type"] == "community" and entry["source_ref_id"] == submission_id]
        self.assertEqual(len(approved_items), 1)
        self.assertEqual(approved_items[0]["display_name"], "Test User")

        media = self.client.get(image_url)
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media.mimetype, "image/png")

    def test_duplicate_submission_is_rejected(self):
        first = self.client.post(
            "/api/community/submit",
            data=self.submit_payload("dot", color=(210, 160, 140)),
            content_type="multipart/form-data",
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/api/community/submit",
            data=self.submit_payload("dot", color=(210, 160, 140)),
            content_type="multipart/form-data",
        )
        self.assertEqual(second.status_code, 409)

    def test_admin_endpoints_require_login(self):
        self.assertEqual(self.client.get("/api/admin/submissions?status=pending").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/playbooks?view=live").status_code, 401)

    def test_reject_and_rank_flow(self):
        submit = self.client.post(
            "/api/community/submit",
            data=self.submit_payload("colorwalk", color=(200, 160, 120)),
            content_type="multipart/form-data",
        )
        submission_id = submit.get_json()["item"]["id"]

        self.admin_login()
        reject = self.client.post(
            f"/api/admin/submissions/{submission_id}/reject",
            json={"review_note": "Not a fit"},
        )
        self.assertEqual(reject.status_code, 200)
        rejected = self.client.get("/api/admin/submissions?status=rejected").get_json()["items"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["review_note"], "Not a fit")

        submit2 = self.client.post(
            "/api/community/submit",
            data=self.submit_payload("dot", color=(100, 160, 220), display_name="Second User", description="Another note"),
            content_type="multipart/form-data",
        )
        submission_id2 = submit2.get_json()["item"]["id"]
        self.client.post(f"/api/admin/submissions/{submission_id2}/approve")
        rank = self.client.post(
            f"/api/admin/submissions/{submission_id2}/rank",
            json={"sort_rank": 10},
        )
        self.assertEqual(rank.status_code, 200)
        approved = self.client.get("/api/admin/submissions?status=approved").get_json()["items"]
        self.assertEqual(approved[0]["sort_rank"], 10)
        unified_items = self.client.get("/api/playbooks?mode=all").get_json()["items"]
        approved_unified = next(item for item in unified_items if item["source_type"] == "community" and item["source_ref_id"] == submission_id2)
        self.assertEqual(approved_unified["sort_rank"], 10)

    def test_submission_prefers_uploaded_rendered_image(self):
        params = {
            "position": "right",
            "block_ratio": 0.4,
            "block_type": "solid",
            "block_color": "[200,180,160]",
            "shape": "circle",
            "dot_size": "20",
            "dot_count": "1",
            "distribution": "manual",
            "manual_positions": json.dumps([[0.5, 0.5]]),
            "text_overlay": "",
            "text_font_size": "16",
            "text_color": "[255,255,255]",
            "format": "PNG",
        }
        submit = self.client.post(
            "/api/community/submit",
            data={
                "image": (self.make_image_bytes(color=(10, 20, 30), size=(80, 80)), "source.png"),
                "rendered_image": (self.make_png_bytes(color=(1, 2, 3), size=(33, 22)), "final.png"),
                "mode": "dot",
                "display_name": "Render User",
                "description": "Rendered upload",
                "website": "",
                "params_json": json.dumps(params),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(submit.status_code, 200)
        item = submit.get_json()["item"]

        self.admin_login()
        self.client.post(f"/api/admin/submissions/{item['id']}/approve")

        media = self.client.get(item["image_url"])
        self.assertEqual(media.status_code, 200)
        saved = Image.open(io.BytesIO(media.data)).convert("RGB")
        self.assertEqual(saved.size, (33, 22))
        self.assertEqual(saved.getpixel((0, 0)), (1, 2, 3))

    def test_admin_can_hide_show_and_reorder_unified_feed(self):
        self.admin_login()
        live_before = self.client.get("/api/admin/playbooks?view=live").get_json()["items"]
        self.assertGreaterEqual(len(live_before), 2)
        first_id = live_before[0]["id"]
        second_id = live_before[1]["id"]

        hide = self.client.post(f"/api/admin/playbooks/{first_id}/hide")
        self.assertEqual(hide.status_code, 200)
        live_after_hide = self.client.get("/api/admin/playbooks?view=live").get_json()["items"]
        self.assertFalse(any(item["id"] == first_id for item in live_after_hide))

        show = self.client.post(f"/api/admin/playbooks/{first_id}/show")
        self.assertEqual(show.status_code, 200)
        live_after_show = self.client.get("/api/admin/playbooks?view=live").get_json()["items"]
        self.assertTrue(any(item["id"] == first_id for item in live_after_show))

        reorder = self.client.post(
            "/api/admin/playbooks/reorder",
            json={"item_ids": [second_id, first_id] + [item["id"] for item in live_after_show if item["id"] not in {first_id, second_id}]},
        )
        self.assertEqual(reorder.status_code, 200)
        live_after_reorder = self.client.get("/api/admin/playbooks?view=live").get_json()["items"]
        self.assertEqual(live_after_reorder[0]["id"], second_id)
        self.assertEqual(live_after_reorder[1]["id"], first_id)


if __name__ == "__main__":
    unittest.main()
