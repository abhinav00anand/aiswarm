# examples/local_adapter.py
import os
import sys
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Security Configuration
API_KEY_NAME = "Authorization"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Optional local API key authentication
ADAPTER_API_KEY = os.getenv("ADAPTER_API_KEY")

def verify_api_key(api_key: str = Security(api_key_header)):
    if ADAPTER_API_KEY:
        if not api_key or not api_key.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
        token = api_key.split(" ")[1]
        if token != ADAPTER_API_KEY:
            raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

# Lazy import transformers to avoid startup delays
transformers_loaded = False
tokenizer = None
model = None
generator = None

MODEL_NAME = os.getenv("ADAPTER_MODEL_NAME", "distilgpt2")

def get_generator():
    global transformers_loaded, tokenizer, model, generator
    if not transformers_loaded:
        print(f"Loading Hugging Face model: {MODEL_NAME}...", file=sys.stderr)
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
            import torch
        except ImportError:
            raise RuntimeError("Required packages 'transformers' or 'torch' are not installed. Run: pip install transformers torch")
            
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        # Safe default padding token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            
        device = 0 if torch.cuda.is_available() else -1
        model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
        if device >= 0:
            model = model.to("cuda")
            print("Loaded model to GPU/CUDA.", file=sys.stderr)
        else:
            print("Loaded model to CPU.", file=sys.stderr)
            
        generator = pipeline("text-generation", model=model, tokenizer=tokenizer, device=device)
        transformers_loaded = True
    return generator

# FastAPI Setup
app = FastAPI(
    title="AISwarm Local HF Adapter",
    description="Secure, OpenAI-compatible proxy for lightweight local HuggingFace inference",
    version="1.0.0"
)

# CORS Policy - strictly bound to localhost for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Request/Response Schemas
class CompletionRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = Field(default=128, ge=1, le=1024)
    temperature: Optional[float] = Field(default=0.2, ge=0.0, le=2.0)
    stop: Optional[List[str]] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessage]
    max_tokens: Optional[int] = Field(default=128, ge=1, le=1024)
    temperature: Optional[float] = Field(default=0.2, ge=0.0, le=2.0)
    stop: Optional[List[str]] = None

@app.get("/health")
async def health():
    return {"status": "healthy", "model": MODEL_NAME}

@app.get("/v1/models", dependencies=[Depends(verify_api_key)])
async def get_models():
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": 1686935002,
                "owned_by": "huggingface"
            }
        ]
    }

@app.post("/v1/completions", dependencies=[Depends(verify_api_key)])
async def completions(req: CompletionRequest):
    gen = get_generator()
    prompt = req.prompt.strip()
    
    # Run pipeline
    out = gen(
        prompt,
        max_new_tokens=req.max_tokens or 128,
        temperature=req.temperature or 0.2,
        do_sample=req.temperature > 0.0,
        num_return_sequences=1,
    )
    
    text = out[0]["generated_text"]
    # Strip prompt if HuggingFace pipeline returns it
    if text.startswith(prompt):
        text = text[len(prompt):]
        
    return {
        "id": "cmpl-local-1",
        "object": "text_completion",
        "choices": [{"text": text, "index": 0, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": len(prompt) // 4,
            "completion_tokens": len(text) // 4,
            "total_tokens": (len(prompt) + len(text)) // 4
        }
    }

@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(req: ChatCompletionRequest):
    # Formulate a cohesive prompt from chat messages
    prompt_parts = []
    for msg in req.messages:
        prompt_parts.append(f"{msg.role.capitalize()}: {msg.content}")
    prompt_parts.append("Assistant:")
    prompt = "\n".join(prompt_parts)
    
    gen = get_generator()
    out = gen(
        prompt,
        max_new_tokens=req.max_tokens or 128,
        temperature=req.temperature or 0.2,
        do_sample=req.temperature > 0.0,
        num_return_sequences=1,
    )
    
    text = out[0]["generated_text"]
    if text.startswith(prompt):
        text = text[len(prompt):]
        
    # Strip any trailing role prefix templates if generated
    text = text.split("\nUser:")[0].split("\nAssistant:")[0].strip()
        
    return {
        "id": "chatcmpl-local-1",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(prompt) // 4,
            "completion_tokens": len(text) // 4,
            "total_tokens": (len(prompt) + len(text)) // 4
        }
    }

if __name__ == "__main__":
    host = os.getenv("ADAPTER_HOST", "127.0.0.1")
    port = int(os.getenv("ADAPTER_PORT", "8000"))
    
    # Warn if host is not localhost
    if host not in ("127.0.0.1", "localhost"):
        print(f"[SECURITY WARNING] Binding to {host} is insecure on public notebook environments.", file=sys.stderr)
        
    uvicorn.run(app, host=host, port=port)
