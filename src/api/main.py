from fastapi import FastAPI
from src.api.routes import router

app = FastAPI(title="Credit Risk Scoring Service")
app.include_router(router)