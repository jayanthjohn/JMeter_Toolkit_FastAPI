
from fastapi import APIRouter, Form
from app.core.regex import get_regex_matches

router = APIRouter()

@router.post("/regex")
def test_regex(pattern: str = Form(...), test_str: str = Form(...)):
    matches = get_regex_matches(pattern, test_str)
    return {"matches": matches}
