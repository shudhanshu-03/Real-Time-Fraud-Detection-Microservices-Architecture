from fastapi import APIRouter
from grpc_server import reload_rules_cache
from db import fetch_active_rules

router = APIRouter()


@router.get("/")
async def get_rules():
    """Retrieve all active rules directly from DB."""
    rules = await fetch_active_rules()
    return {"rules": rules, "count": len(rules)}


@router.post("/reload")
async def trigger_reload():
    """Manually trigger a reload of the rule cache across the service."""
    await reload_rules_cache()
    return {"status": "success", "message": "Rule cache reloaded"}


# For CRUD, we would normally inject DB session here and do inserts/updates.
# Left as an exercise for production extension since requirements focus on evaluation.
