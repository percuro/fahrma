"""Receipt photos: attaching, showing, deleting, limits per plan, files on disk."""

import io
import os
import time
import unittest
import zipfile
from unittest import mock

from app import config
from app.models.receipt import Receipt
from app.services import receipt_store
from app.services.receipt_image import InvalidImage, image_size
from tests.support import JPEG_HEADERS, PASSWORD, jpeg
from tests.test_accounts import code
from tests.test_api import GroupSetupMixin
from tests.test_plans import HostingTestCase

EXPENSE = {"date": "2026-11-15", "category": "repair", "amount_cents": 25000, "allocation": "equal"}


def webp_vp8x(width: int, height: int) -> bytes:
    body = b"VP8X" + (10).to_bytes(4, "little") + b"\x00" * 4
    body += (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + body


class ImageCheckTests(unittest.TestCase):
    def test_jpeg_size(self):
        self.assertEqual(image_size(jpeg(1200, 1600), "image/jpeg"), (1200, 1600))

    def test_webp_size(self):
        self.assertEqual(image_size(webp_vp8x(1600, 900), "image/webp"), (1600, 900))

    def test_refused(self):
        cases = [
            (b"<html><script>alert(1)</script></html>", "image/jpeg"),
            (b"\xff\xd8\xff\xd9", "image/jpeg"),  # no frame
            (jpeg(), "image/webp"),  # type does not match
            (b"GIF89a" + b"\x00" * 20, "image/gif"),
            (jpeg(20000, 10), "image/jpeg"),
        ]
        for data, content_type in cases:
            with self.subTest(content_type=content_type, start=data[:6]), self.assertRaises(InvalidImage):
                image_size(data, content_type)


class ReceiptConfigTests(unittest.TestCase):
    def env(self, **values):
        return mock.patch.dict(os.environ, {"RECEIPTS_DIR": "", "MAX_RECEIPT_KB": "", **values})

    def test_directory_next_to_the_database(self):
        with self.env(DATABASE_URL="sqlite:////data/carshare.db"):
            self.assertEqual(str(config.get_receipts_dir()), "/data/receipts")
        with self.env(DATABASE_URL="sqlite:///:memory:"), self.assertRaises(config.ConfigError):
            config.get_receipts_dir()
        with self.env(RECEIPTS_DIR="/srv/photos", DATABASE_URL="postgresql://x"):
            self.assertEqual(str(config.get_receipts_dir()), "/srv/photos")

    def test_max_size(self):
        with self.env():
            self.assertEqual(config.get_max_receipt_bytes(), 3 * 1024 * 1024)
        with self.env(MAX_RECEIPT_KB="500"):
            self.assertEqual(config.get_max_receipt_bytes(), 500 * 1024)
        for value in ("50", "big"):
            with self.subTest(value=value), self.env(MAX_RECEIPT_KB=value), self.assertRaises(config.ConfigError):
                config.get_max_receipt_bytes()

    def test_plan_file_takes_the_storage_limit(self):
        plans = config._parse_plans('{"default": "a", "plans": [{"id": "a", "name": "A", "receipt_mb_per_group": 50}]}')
        self.assertEqual(plans.default_plan.receipt_mb_per_group, 50)


class ReceiptTests(GroupSetupMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.entry = self.fuel(self.alex, 6000, self.alex_id)
        self.url = f"{self.base}/fuel/{self.entry['id']}/receipts"

    def upload(self, client=None, url=None, data=None, headers=None, expect=201):
        response = (client or self.sam).post(url or self.url, content=data or jpeg(), headers=headers or JPEG_HEADERS)
        self.assertEqual(response.status_code, expect, response.text)
        return response

    def files(self) -> list[str]:
        directory = self.env.receipts_dir / str(self.gid)
        return sorted(path.name for path in directory.iterdir()) if directory.is_dir() else []

    def test_attach_show_delete(self):
        receipt = self.upload().json()
        self.assertEqual((receipt["width"], receipt["height"], receipt["content_type"]), (1200, 1600, "image/jpeg"))
        self.assertEqual(receipt["created_by"], self.sam_id)
        entry = self.alex.get(f"{self.base}/fuel/{self.entry['id']}").json()
        self.assertEqual([r["id"] for r in entry["receipts"]], [receipt["id"]])
        listed = self.alex.get(f"{self.base}/fuel").json()[0]
        self.assertEqual(len(listed["receipts"]), 1)
        self.assertEqual(len(self.files()), 1)

        image = self.alex.get(f"{self.base}/receipts/{receipt['id']}")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content, jpeg())
        self.assertEqual(image.headers["content-type"], "image/jpeg")
        self.assertEqual(image.headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", image.headers["content-security-policy"])
        self.assertIn("default-src 'none'", image.headers["content-security-policy"])
        self.assertEqual(image.headers["cache-control"], "private, no-cache")
        self.assertTrue(image.headers["content-disposition"].startswith("inline"))

        self.assertEqual(self.alex.delete(f"{self.base}/receipts/{receipt['id']}").status_code, 204)
        self.assertEqual(self.files(), [])
        self.assertEqual(self.alex.get(f"{self.base}/receipts/{receipt['id']}").status_code, 404)
        actions = [(e["entity"], e["action"]) for e in self.alex.get(f"{self.base}/audit").json()]
        self.assertIn(("receipt", "create"), actions)
        self.assertIn(("receipt", "delete"), actions)

    def test_expense(self):
        expense = self.alex.post(f"{self.base}/expenses", json={**EXPENSE, "paid_by_user_id": self.alex_id}).json()
        self.upload(url=f"{self.base}/expenses/{expense['id']}/receipts", data=webp_vp8x(800, 600),
                    headers={"Content-Type": "image/webp"})  # fmt: skip
        receipts = self.alex.get(f"{self.base}/expenses/{expense['id']}").json()["receipts"]
        self.assertEqual([(r["width"], r["content_type"]) for r in receipts], [(800, "image/webp")])
        self.assertTrue(self.files()[0].endswith(".webp"))

    def test_refused_uploads(self):
        response = self.upload(data=b"<svg/>", headers={"Content-Type": "image/svg+xml"}, expect=415)
        self.assertEqual(code(response, 415), "receipt_type")
        response = self.upload(data=b"\xff\xd8\xff" + b"x" * 100, expect=422)
        self.assertEqual(code(response, 422), "receipt_invalid")
        with mock.patch.dict(os.environ, {"MAX_RECEIPT_KB": "100"}):
            response = self.upload(data=jpeg(size=101 * 1024), expect=413)
        self.assertEqual(code(response, 413), "receipt_too_large")
        self.assertEqual(response.json()["detail"]["params"], {"max_kb": 100})
        self.upload(url=f"{self.base}/fuel/999/receipts", expect=404)
        self.assertEqual(self.files(), [])

    def test_at_most_five_per_entry(self):
        for _ in range(5):
            self.upload()
        self.assertEqual(code(self.upload(expect=409), 409), "receipt_count")
        self.assertEqual(len(self.files()), 5)

    def test_settled_entry_takes_photos_but_keeps_them(self):
        receipt = self.upload().json()
        self.trip(self.alex, 10000, 10100, [(self.alex_id, 1)])
        settle = {"period_end": "2026-11-20", "accept_warnings": True}
        self.assertEqual(self.alex.post(f"{self.base}/settlements", json=settle).status_code, 201)
        self.upload()
        response = self.alex.delete(f"{self.base}/receipts/{receipt['id']}")
        self.assertEqual(code(response, 409), "already_settled")
        self.assertEqual(len(self.files()), 2)

    def test_idempotency_key(self):
        headers = {**JPEG_HEADERS, "Idempotency-Key": "draft-1234-r1"}
        first = self.upload(headers=headers)
        again = self.upload(headers=headers, expect=200)
        self.assertEqual(again.headers["Idempotent-Replayed"], "true")
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual(len(self.files()), 1)
        # The same key for an entry is refused
        fuel = {"car_id": self.car_id, "date": "2026-11-12", "amount_cents": 100, "paid_by_user_id": self.sam_id}
        response = self.sam.post(f"{self.base}/fuel", json=fuel, headers={"Idempotency-Key": "draft-1234-r1"})
        self.assertEqual(code(response, 422), "idempotency_key_reused")

    def test_deleting_the_entry_removes_its_photos(self):
        self.upload()
        self.upload()
        self.assertEqual(self.alex.delete(f"{self.base}/fuel/{self.entry['id']}").status_code, 204)
        self.assertEqual(self.files(), [])
        db = self.env.SessionLocal()
        try:
            self.assertEqual(db.query(Receipt).count(), 0)
        finally:
            db.close()

    def test_deleting_the_group_removes_its_directory(self):
        self.upload()
        response = self.alex.request("DELETE", self.base, json={"name": "Test group"})
        self.assertEqual(response.status_code, 204, response.text)
        self.assertFalse((self.env.receipts_dir / str(self.gid)).exists())

    def test_deleting_an_account_with_its_own_group(self):
        solo = self.sam.post("/v1/groups", json={"name": "Solo"}).json()["id"]
        car = self.sam.post(f"/v1/groups/{solo}/cars", json={"name": "Mine", "start_odometer_km": 0}).json()
        fuel = self.sam.post(
            f"/v1/groups/{solo}/fuel",
            json={"car_id": car["id"], "date": "2026-11-12", "amount_cents": 100, "paid_by_user_id": self.sam_id},
        ).json()
        self.upload(url=f"/v1/groups/{solo}/fuel/{fuel['id']}/receipts")
        kept = self.upload().json()  # in the group that lives on
        response = self.sam.request("DELETE", "/v1/account", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 204, response.text)
        self.assertFalse((self.env.receipts_dir / str(solo)).exists())
        self.assertEqual(self.alex.get(f"{self.base}/receipts/{kept['id']}").status_code, 200)

    def test_failed_commit_leaves_no_file(self):
        with mock.patch("app.services.receipt_service.idempotency.commit", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertEqual(self.files(), [])

    def test_sweep_removes_only_old_files_without_a_row(self):
        kept = self.upload().json()
        directory = self.env.receipts_dir / str(self.gid)
        leftover, fresh = "a" * 32 + ".jpg", "b" * 32 + ".jpg"
        (directory / leftover).write_bytes(b"x")
        (directory / fresh).write_bytes(b"x")
        (directory / "notes.txt").write_bytes(b"not ours")
        foreign = self.env.receipts_dir / "photos"
        foreign.mkdir()
        (foreign / ("c" * 32 + ".jpg")).write_bytes(b"not ours either")
        gone = self.env.receipts_dir / "999"
        gone.mkdir()
        old = time.time() - 2 * receipt_store.ORPHAN_AGE_SECONDS
        for path in (directory / leftover, directory / "notes.txt", foreign / ("c" * 32 + ".jpg")):
            os.utime(path, (old, old))
        db = self.env.SessionLocal()
        try:
            self.assertEqual(receipt_store.sweep(db), 1)
        finally:
            db.close()
        # The photo, the fresh file and the file fahrma did not write stay
        self.assertEqual(len(self.files()), 3)
        self.assertIn(fresh, self.files())
        self.assertNotIn(leftover, self.files())
        self.assertTrue((foreign / ("c" * 32 + ".jpg")).exists())
        self.assertFalse(gone.exists())
        self.assertEqual(self.alex.get(f"{self.base}/receipts/{kept['id']}").status_code, 200)

    def test_zip_download(self):
        self.upload()
        self.upload()
        expense = self.alex.post(f"{self.base}/expenses", json={**EXPENSE, "paid_by_user_id": self.alex_id}).json()
        self.upload(url=f"{self.base}/expenses/{expense['id']}/receipts")
        response = self.sam.get(f"{self.base}/receipts.zip")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("attachment", response.headers["content-disposition"])
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        fuel_id, expense_id = self.entry["id"], expense["id"]
        self.assertEqual(
            archive.namelist(),
            [f"2026-11-12_fuel_{fuel_id}_1.jpg", f"2026-11-12_fuel_{fuel_id}_2.jpg",
             f"2026-11-15_repair_{expense_id}_1.jpg"],
        )  # fmt: skip
        self.assertEqual(archive.read(archive.namelist()[0]), jpeg())

    def test_empty_zip(self):
        response = self.sam.get(f"{self.base}/receipts.zip")
        self.assertEqual(zipfile.ZipFile(io.BytesIO(response.content)).namelist(), [])

    def test_export_lists_photos_without_their_place_on_disk(self):
        self.upload()
        data = self.alex.get(f"{self.base}/export.json").json()
        self.assertEqual(len(data["receipts"]), 1)
        self.assertNotIn("file", data["receipts"][0])
        self.assertEqual(data["receipts"][0]["fuel_id"], self.entry["id"])

    def test_turned_off(self):
        receipt = self.upload().json()
        with mock.patch.dict(os.environ, {"RECEIPTS": "off"}):
            self.assertEqual(code(self.upload(expect=404), 404), "receipts_off")
            self.assertEqual(self.alex.get(f"{self.base}/receipts/{receipt['id']}").status_code, 404)
            self.assertFalse(self.env.client(None).get("/v1/meta").json()["receipts"])
        self.assertTrue(self.env.client(None).get("/v1/meta").json()["receipts"])


class ReceiptPlanTests(HostingTestCase):
    """The free plan of tests.test_plans allows 1 MB of photos."""

    def setUp(self):
        super().setUp()
        self.entry = self.fuel(self.alex, 6000, self.alex_id)
        self.url = f"{self.base}/fuel/{self.entry['id']}/receipts"

    def upload(self, size, expect=201):
        response = self.alex.post(self.url, content=jpeg(size=size), headers=JPEG_HEADERS)
        self.assertEqual(response.status_code, expect, response.text)
        return response

    def test_storage_limit_and_usage(self):
        first = self.upload(600 * 1024).json()
        response = self.upload(500 * 1024, expect=409)
        self.assertEqual(code(response, 409), "limit_reached")
        params = response.json()["detail"]["params"]
        self.assertEqual(params, {"limit": "receipt_mb_per_group", "max": 1, "plan": "free"})
        self.upload(400 * 1024)
        usage = self.alex.get(self.base).json()["plan"]["usage"]
        self.assertEqual(usage["receipt_mb_per_group"], 1.0)
        # Deleting makes room
        self.assertEqual(self.alex.delete(f"{self.base}/receipts/{first['id']}").status_code, 204)
        self.upload(500 * 1024)

    def test_downgrade_keeps_photos(self):
        self.set_plan("plus")  # unlimited storage
        receipt = self.upload(900 * 1024).json()
        self.upload(900 * 1024)
        self.set_plan(None)  # back to free: 1.8 MB stored, 1 MB allowed
        self.assertEqual(self.alex.get(f"{self.base}/receipts/{receipt['id']}").status_code, 200)
        self.assertEqual(code(self.upload(2000, expect=409), 409), "limit_reached")
        self.assertEqual(len(self.alex.get(f"{self.base}/fuel/{self.entry['id']}").json()["receipts"]), 2)


if __name__ == "__main__":
    unittest.main()
