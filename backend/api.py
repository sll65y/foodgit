from contextlib import asynccontextmanager
from datetime import date, timedelta
from io import BytesIO
import os
from pathlib import Path as FilePath
import re
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from .agent import generate_plan
from .documents import LocalDocuments, MongoDocuments
from .models import DishInput, Login, Meal, PlanRequest, Profile, Record
from .nutrition import calculate_targets
from .storage import MEALS, NUTRIENTS, Invalid, Store


ROOT = FilePath(__file__).resolve().parents[1]
MAX_UPLOAD = 5 * 1024 * 1024
PAGE = Annotated[int, Query(ge=1, le=100_000)]
SIZE = Annotated[int, Query(ge=1, le=100)]
ID = Annotated[int, Path(gt=0, le=2_147_483_647)]


def paginated(items, total, page, size):
    return {"items": items, "total": total, "page": page, "size": size}


def dashboard_stats(store, user_id, end, days):
    start = end - timedelta(days=days - 1)
    rows = store.daily_meals(user_id, start.isoformat(), end.isoformat())
    index = {(row["eaten_on"], row["meal"]): row for row in rows}
    grid = []
    for step in range(days):
        day = (start + timedelta(days=step)).isoformat()
        meals = {}
        for meal in MEALS:
            row = index.get((day, meal), {})
            meals[meal] = {"entries": row.get("entries", 0), **{n: round(row.get(n, 0), 1) for n in NUTRIENTS}}
        grid.append({
            "date": day, "meals": meals,
            "total": {n: round(sum(meal[n] for meal in meals.values()), 1) for n in NUTRIENTS},
        })
    return {
        "days": grid, "recorded_days": len({row["eaten_on"] for row in rows}),
        "records": sum(row["entries"] for row in rows),
        "totals": {key: round(sum(row[key] for row in rows), 1) for key in NUTRIENTS},
    }


def save_image(content, images, dish_id, store):
    try:
        with Image.open(BytesIO(content), formats=("JPEG", "PNG", "WEBP")) as source:
            if source.width * source.height > 16_000_000 or getattr(source, "is_animated", False):
                raise Invalid("请上传 1600 万像素以内的静态图片。")
            source = ImageOps.exif_transpose(source)
            source.thumbnail((720, 540))
            source = source.convert("RGBA")
            image = Image.new("RGB", source.size, "white")
            image.paste(source, mask=source.getchannel("A"))
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise Invalid("图片无法读取，请上传有效的 JPG、PNG 或 WebP。") from exc

    key = f"dish-{dish_id}.jpg"
    if not store.set_image(dish_id, key):
        raise HTTPException(404, "菜品不存在。")
    temp = images / f".{uuid4().hex}.tmp"
    try:
        image.save(temp, "JPEG", quality=85, optimize=True)
        temp.replace(images / key)
    finally:
        temp.unlink(missing_ok=True)
    return {"image_url": f"/images/{key}"}


def create_app(data_dir=None):
    data_dir = FilePath(data_dir or os.environ.get("FOOD_DATA_DIR", ROOT / "runtime"))
    images = data_dir / "images"
    store = Store(data_dir / "food.sqlite3")

    @asynccontextmanager
    async def lifespan(app):
        images.mkdir(parents=True, exist_ok=True)
        store.initialize()
        mongo_uri = os.environ.get("FOOD_MONGO_URI")
        docs = MongoDocuments(mongo_uri) if mongo_uri else LocalDocuments(data_dir / "plans")
        app.state.documents = docs
        try:
            yield
        finally:
            if isinstance(docs, MongoDocuments):
                docs.client.close()

    app = FastAPI(title="食序 · 饮食规划 API", version="0.1.0", lifespan=lifespan)
    bearer = HTTPBearer(auto_error=False)

    def session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        token = credentials.credentials if credentials else ""
        user = store.user(token) if 30 < len(token) < 80 else None
        if not user:
            raise HTTPException(401, "请先登录。", headers={"WWW-Authenticate": "Bearer"})
        return user, token

    def member(active=Depends(session)):
        return active[0]

    def admin(user=Depends(member)):
        if user["role"] != "admin":
            raise HTTPException(403, "只有管理员可以维护菜库。")
        return user

    @app.exception_handler(Invalid)
    async def on_invalid(_request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def on_validation(_request, exc):
        errors = [{key: item[key] for key in ("loc", "msg", "type")} for item in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "plan_store": app.state.documents.kind, "date": date.today().isoformat()}

    @app.post("/api/auth/login")
    def login(payload: Login):
        token = store.login(payload.username, payload.password)
        if not token:
            raise HTTPException(401, "账号或密码不正确。")
        return {"token": token, "user": store.user(token)}

    @app.post("/api/auth/logout", status_code=204)
    def logout(active=Depends(session)):
        store.logout(active[1])

    @app.get("/api/me")
    def me(user=Depends(member)):
        return user

    @app.get("/api/profile")
    def profile(user=Depends(member)):
        return store.profile(user["id"])

    @app.put("/api/profile")
    def update_profile(payload: Profile, user=Depends(member)):
        store.save_profile(user["id"], payload.model_dump())
        return store.profile(user["id"])

    @app.get("/api/targets")
    def targets(user=Depends(member)):
        return calculate_targets(store.profile(user["id"]))

    @app.get("/api/ingredients")
    def ingredients(_user=Depends(member)):
        return store.ingredients()

    @app.get("/api/dishes")
    def dishes(_user=Depends(member), meal: Meal | None = None, q: str = Query("", max_length=48),
               page: PAGE = 1, size: SIZE = 8):
        rows, total = store.dishes(meal, q.strip(), page, size)
        return paginated(rows, total, page, size)

    @app.post("/api/dishes", status_code=201)
    def add_dish(payload: DishInput, _admin=Depends(admin)):
        return {"id": store.create_dish(payload.model_dump())}

    @app.put("/api/dishes/{dish_id}/image")
    async def upload_image(dish_id: ID, request: Request, _admin=Depends(admin)):
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_UPLOAD:
                raise HTTPException(413, "图片不能超过 5 MB。")
            data.extend(chunk)
        return await run_in_threadpool(save_image, data, images, dish_id, store)

    @app.post("/api/plans", status_code=201)
    def create_plan(payload: PlanRequest, user=Depends(member)):
        result = generate_plan(store, user["id"], payload.model_dump())
        return app.state.documents.save(user["id"], result)

    @app.get("/api/plans")
    def plans(user=Depends(member), page: PAGE = 1, size: SIZE = 8):
        docs, total = app.state.documents.list(user["id"], (page - 1) * size, size)
        summaries = [{k: doc[k] for k in ("id", "created_at", "request", "status", "totals")} for doc in docs]
        return paginated(summaries, total, page, size)

    @app.get("/api/plans/{plan_id}")
    def plan(plan_id: str, user=Depends(member)):
        if not re.fullmatch("[0-9a-f]{32}", plan_id):
            raise HTTPException(404, "方案不存在。")
        doc = app.state.documents.get(user["id"], plan_id)
        if not doc:
            raise HTTPException(404, "方案不存在。")
        return doc

    @app.get("/api/records")
    def records(user=Depends(member), page: PAGE = 1, size: SIZE = 8):
        rows, total = store.records(user["id"], page, size)
        return paginated(rows, total, page, size)

    @app.post("/api/records", status_code=201)
    def log_record(payload: Record, user=Depends(member)):
        return {"id": store.log_meal(user["id"], payload.model_dump())}

    @app.delete("/api/records/{record_id}", status_code=204)
    def delete_record(record_id: ID, user=Depends(member)):
        if not store.delete_record(user["id"], record_id):
            raise HTTPException(404, "记录不存在。")

    @app.get("/api/stats")
    def stats(user=Depends(member), days: int = Query(7, ge=1, le=30)):
        return dashboard_stats(store, user["id"], date.today(), days)

    app.mount("/images", StaticFiles(directory=images, check_dir=False), name="images")
    app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
    return app
