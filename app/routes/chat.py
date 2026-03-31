"""
Chat Routes - /v1/chat/completions
"""

import json
import time

import litellm
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import app.database as db

router = APIRouter(prefix="/v1", tags=["chat"])


class ChatMsg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    model: str
    messages: list[ChatMsg]
    stream: bool = False


async def verify_client_key(key: str = None):
    """Verify client API key."""
    return {"allowed_models": None}


@router.post("/chat/completions")
async def chat_completions(req: ChatReq, key_info: dict = Depends(verify_client_key)):
    """OpenAI-compatible chat completions endpoint using LiteLLM"""
    allowed = key_info.get("allowed_models")
    if allowed:
        if req.model not in [x.strip() for x in allowed.split(",") if x.strip()]:
            return JSONResponse({"error": "Model not allowed"}, 403)

    source_map = {
        "gpt": "chatgpt",
        "o1-": "chatgpt",
        "claude": "claude",
        "gemini": "gemini",
        "deepseek": "deepseek",
        "moonshot": "moonshot",
        "qwen": "qwen",
    }
    target_source = "chatgpt"
    for k, v in source_map.items():
        if k in req.model:
            target_source = v
            break

    pool = db.get_pool_data_sync(target_source)
    api_key = None
    if pool:
        t = pool.get("tokens", {})
        api_key = t.get("apiKey") or t.get("key") or t.get("token")

    try:
        response = await litellm.acompletion(
            model=req.model,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            stream=req.stream,
            timeout=60,
            api_key=api_key,
        )
    except Exception as e:
        return JSONResponse({"error": f"LiteLLM Error: {str(e)}"}, 500)

    if req.stream:

        async def stream_gen():
            try:
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        yield f"data: {json.dumps({'id': chunk.id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': req.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(stream_gen(), media_type="text/event-stream")
    else:
        return {
            "id": response.id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response.choices[0].message.content},
                    "finish_reason": response.choices[0].finish_reason,
                }
            ],
        }


@router.get("/models")
async def list_models():
    """List available models."""
    models = db.get_all_models_sync()
    data = []
    for m in models:
        data.append(
            {
                "id": m["name"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": m["source"],
            }
        )
    return {"object": "list", "data": data}
