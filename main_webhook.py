from fastapi import FastAPI

fastapi_app = FastAPI()

@fastapi_app.get("/health")
async def health():
    return {"status": "ok"}
