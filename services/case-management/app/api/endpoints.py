from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.case import Case, CaseNote
from pydantic import BaseModel

router = APIRouter()


import uuid
from pydantic import BaseModel

class NoteCreate(BaseModel):
    author: str
    content: str


class CaseUpdate(BaseModel):
    status: str
    assigned_to: str = None

class CaseCreate(BaseModel):
    alert_ids: list[str] = []
    status: str = "OPEN"
    severity: str = "HIGH"
    priority: str = None
    title: str = None
    description: str = None
    assigned_to: str = None


@router.get("/cases")
async def list_cases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).limit(100))
    cases = result.scalars().all()
    return [
        {
            "case_id": c.case_id,
            "alert_id": c.alert_id,
            "transaction_id": c.transaction_id,
            "customer_id": c.customer_id,
            "status": c.status,
            "severity": c.severity,
            "assigned_to": c.assigned_to,
            "created_at": c.created_at,
        }
        for c in cases
    ]


@router.get("/cases/{case_id}")
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).filter(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    notes_result = await db.execute(select(CaseNote).filter(CaseNote.case_id == case_id))
    notes = notes_result.scalars().all()

    return {
        "case_id": case.case_id,
        "alert_id": case.alert_id,
        "transaction_id": case.transaction_id,
        "customer_id": case.customer_id,
        "status": case.status,
        "severity": case.severity,
        "assigned_to": case.assigned_to,
        "created_at": case.created_at,
        "notes": [
            {"note_id": n.note_id, "author": n.author, "content": n.content, "created_at": n.created_at} for n in notes
        ],
    }


@router.post("/cases/{case_id}/notes")
async def add_case_note(case_id: str, note: NoteCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).filter(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    new_note = CaseNote(case_id=case_id, author=note.author, content=note.content)
    db.add(new_note)
    await db.commit()
    return {"status": "success", "note_id": new_note.note_id}


@router.patch("/cases/{case_id}")
async def update_case(case_id: str, update_data: CaseUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).filter(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.status = update_data.status
    if update_data.assigned_to:
        case.assigned_to = update_data.assigned_to

    db.add(case)
    await db.commit()
    return {"status": "success", "case_id": case.case_id}

@router.post("/cases", status_code=201)
async def create_case(case_in: CaseCreate, db: AsyncSession = Depends(get_db)):
    primary_alert_id = case_in.alert_ids[0] if case_in.alert_ids else f"alt_{uuid.uuid4().hex[:16]}"
    
    new_case = Case(
        alert_id=primary_alert_id,
        transaction_id=f"tx_{uuid.uuid4().hex[:16]}",
        customer_id=f"CUST-{uuid.uuid4().hex[:8]}",
        severity=case_in.priority.upper() if case_in.priority else case_in.severity.upper(),
        status=case_in.status.upper(),
        assigned_to=case_in.assigned_to
    )
    db.add(new_case)
    await db.flush()
    
    if case_in.title or case_in.description:
        note_content = f"[{case_in.title}] {case_in.description}" if case_in.title else case_in.description
        if note_content:
            new_note = CaseNote(
                case_id=new_case.case_id,
                author="System Seed",
                content=note_content
            )
            db.add(new_note)
            
    await db.commit()
    return {"status": "success", "case_id": new_case.case_id}
