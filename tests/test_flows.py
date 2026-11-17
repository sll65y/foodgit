from datetime import date
from io import BytesIO
from pathlib import Path
from shutil import rmtree
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

from backend.api import create_app


class FoodFlows(unittest.TestCase):
    def setUp(self):
        root = (Path(__file__).resolve().parents[1] / "runtime").resolve()
        root.mkdir(exist_ok=True)
        directory = root / f"test-{uuid4().hex}"
        directory.mkdir()
        self.addCleanup(self.cleanup_scratch, root, directory)
        # Keep tests isolated from any personal Mongo configuration.
        self.enterContext(patch.dict("os.environ", {"FOOD_MONGO_URI": ""}))
        self.client = self.enterContext(TestClient(create_app(directory)))
        self.member = self.sign_in("demo")

    @staticmethod
    def cleanup_scratch(root, directory):
        target = directory.resolve()
        if target.parent == root and target.name.startswith("test-"):
            rmtree(target)

    def sign_in(self, username):
        res = self.client.post("/api/auth/login", json={"username": username, "password": "food-demo"})
        self.assertEqual(res.status_code, 200)
        return {"Authorization": "Bearer " + res.json()["token"]}

    def test_plan_combines_hard_exclusions_and_persists_result(self):
        items = self.client.get("/api/ingredients", headers=self.member).json()
        by_name = {i["name"]: i["id"] for i in items}
        profile = self.client.get("/api/profile", headers=self.member).json()
        profile["excluded_ingredients"] = [by_name["花生"]]
        res = self.client.put("/api/profile", json=profile, headers=self.member)
        self.assertEqual(res.status_code, 200, res.text)
        res = self.client.post("/api/plans", headers=self.member, json={
            "message": "帮我安排三餐，蛋奶素，不吃辣，对核桃过敏",
            "exclude": [by_name["鸡蛋"]],
        })
        self.assertEqual(res.status_code, 201, res.text)
        plan = res.json()
        self.assertEqual([d["meal"] for d in plan["meals"]], ["breakfast", "lunch", "dinner"])
        forbidden = {by_name[name] for name in ("花生", "核桃", "鸡蛋", "辣椒")}
        forbidden.update(i["id"] for i in items if i["category"] in {"meat", "seafood"})
        selected = {i["id"] for meal in plan["meals"] for i in meal["ingredients"]}
        self.assertFalse(forbidden & selected)
        self.assertAlmostEqual(plan["totals"]["kcal"], sum(d["nutrients"]["kcal"] for d in plan["meals"]), delta=.2)
        self.assertEqual(self.client.get("/api/plans/" + plan["id"], headers=self.member).json(), plan)
        self.assertEqual(self.client.get("/api/plans/" + plan["id"], headers=self.sign_in("admin")).status_code, 404)

    def test_unknown_or_impossible_restrictions_do_not_create_a_plan(self):
        unknown = self.client.post("/api/plans", headers=self.member, json={"message": "不吃芝麻"})
        self.assertEqual(unknown.status_code, 422)
        self.assertIn("芝麻", unknown.json()["detail"])
        items = self.client.get("/api/ingredients", headers=self.member).json()
        impossible = self.client.post("/api/plans", headers=self.member, json={"exclude": [i["id"] for i in items]})
        self.assertEqual(impossible.status_code, 422)
        self.assertIn("早餐", impossible.json()["detail"])
        self.assertEqual(self.client.get("/api/plans", headers=self.member).json()["total"], 0)

    def test_records_drive_statistics_and_are_user_scoped(self):
        admin = self.sign_in("admin")
        today = date.today().isoformat()
        meal = {"dish_id": 1, "eaten_on": today, "meal": "breakfast", "portions": 1.25}
        res = self.client.post("/api/records", json=meal, headers=self.member)
        self.assertEqual(res.status_code, 201, res.text)
        record_url = "/api/records/" + str(res.json()["id"])
        self.assertEqual(self.client.delete(record_url, headers=admin).status_code, 404)
        data = self.client.get("/api/stats", headers=self.member).json()
        self.assertEqual(data["records"], 1)
        self.assertEqual(data["days"][-1]["meals"]["breakfast"]["entries"], 1)
        record = self.client.get("/api/records", headers=self.member).json()["items"][0]
        self.assertAlmostEqual(data["totals"]["kcal"], record["kcal"], delta=.1)
        fresh_plan = self.client.post("/api/plans", headers=self.member, json={}).json()
        self.assertTrue(any("近 7 天饮食记录共 1 条" in line for line in fresh_plan["explanation"]))
        self.assertEqual(self.client.delete(record_url, headers=self.member).status_code, 204)
        self.assertEqual(self.client.get("/api/stats", headers=self.member).json()["records"], 0)

    def test_catalog_pagination_role_and_image_processing(self):
        first, second = [self.client.get("/api/dishes", headers=self.member, params={"page": n, "size": 2}).json()
                         for n in (1, 2)]
        self.assertGreater(first["total"], 2)
        self.assertFalse({d["id"] for d in first["items"]} & {d["id"] for d in second["items"]})
        dish = {"name": "燕麦测试盘", "meal": "breakfast", "flavor": "清淡", "description": "",
                "ingredients": [{"id": 1, "grams": 75}, {"id": 23, "grams": 90}]}
        self.assertEqual(self.client.post("/api/dishes", json=dish, headers=self.member).status_code, 403)
        admin = self.sign_in("admin")
        created = self.client.post("/api/dishes", json=dish, headers=admin)
        self.assertEqual(created.status_code, 201, created.text)
        url = f"/api/dishes/{created.json()['id']}/image"
        sample = BytesIO()
        Image.new("RGBA", (1400, 900), (220, 170, 100, 180)).save(sample, "PNG")
        self.assertEqual(self.client.put(url, content=sample.getvalue(), headers=self.member).status_code, 403)
        self.assertEqual(self.client.put(url, content=b"not an image", headers=admin).status_code, 422)
        res = self.client.put(url, content=sample.getvalue(), headers=admin)
        self.assertEqual(res.status_code, 200, res.text)
        photo = self.client.get(res.json()["image_url"])
        with Image.open(BytesIO(photo.content)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (720, 463))


if __name__ == "__main__":
    unittest.main()
