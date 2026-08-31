from fastapi import FastAPI
from .auth.routes import router as auth_router

app = FastAPI(title="AI-Driven Product Assistant - Milestone 1 Backend")

app.include_router(auth_router)

@app.get("/")
async def root():
    return {"status": "ok"}
