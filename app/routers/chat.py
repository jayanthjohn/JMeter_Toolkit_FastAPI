####replace the the chat.py if you geet error with llma
 
from fastapi import APIRouter, Form
router = APIRouter()
# ─── Try to load the real offline LLM ──────────────────────────────
try:
   from app.core.llm_engine.run_local_llm import generate_with_prompt
   LLM_AVAILABLE = True
except Exception:
   LLM_AVAILABLE = False
   # stub so the rest of the code still works
   def generate_with_prompt(prompt: str) -> str:
       return (
           "⚠️  Offline LLM is disabled for this demo.\n"
           "Ask me anything about JMeter and I'll reply with a canned answer!"
       )
@router.post("/chat")
def chat(user_prompt: str = Form(...)):
   answer = generate_with_prompt(user_prompt)
   return {"response": answer}