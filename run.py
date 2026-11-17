import argparse

import uvicorn

from backend.api import create_app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="食序 · 本地饮食规划原型")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
