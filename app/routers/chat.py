
from fastapi import APIRouter, Form
from app.core.llm_engine.run_local_llm import generate_with_prompt

router = APIRouter()

@router.post("/chat")
def chat(user_prompt: str = Form(...)):
    answer = generate_with_prompt(user_prompt)
    return {"response": answer}
