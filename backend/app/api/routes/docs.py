"""
Documentation API routes
"""
from fastapi import APIRouter, HTTPException

from app.api.deps import DOCS_PATH
from app.core.utils import is_valid_identifier

router = APIRouter()


@router.get("")
async def list_docs():
    """List available documentation files"""
    if not DOCS_PATH.exists():
        return {"docs": []}
    
    docs = []
    for f in sorted(DOCS_PATH.glob("*.md")):
        docs.append({
            "id": f.stem,
            "filename": f.name
        })
    return {"docs": docs}


@router.get("/{doc_id}")
async def get_doc(doc_id: str):
    """Get documentation content by ID"""
    if not is_valid_identifier(doc_id):
        raise HTTPException(status_code=400, detail="Invalid document ID")
    
    doc_path = DOCS_PATH / f"{doc_id}.md"
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    content = doc_path.read_text(encoding="utf-8")
    return {"id": doc_id, "content": content}
