# llm_engine/run_local_llm.py

# Load the Misteral model
from llama_cpp import Llama

llm = Llama(
    model_path="models/mistral-7b-instruct-v0.1.Q4_K_M.gguf",
    n_ctx=4096,          # cut to 1024 if RAM tight; raise to 4096 on 16-32 GB
    n_threads=6          # or 6 for M2
)

def generate_with_prompt(prompt: str, max_tokens: int = 300) -> str:
    try:
        result = llm(prompt=prompt, max_tokens=max_tokens, stop=["</s>", "###", "User:", "Assistant:"])
        return result["choices"][0]["text"].strip()
    except Exception as e:
        return f"LLM Error: {e}"