from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.routes import transactions, stream, metrics
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    stream.start_kafka_consumer()
    yield
    stream.stop_kafka_consumer()

app = FastAPI(title="API Gateway", lifespan=lifespan)

# Allow CORS for the dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")

@app.get("/health")
def health(): return {"status": "ok"}
