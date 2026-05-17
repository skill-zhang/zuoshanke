"""SSE 流式响应工具 — 消除 4 次重复的 StreamingResponse 样板"""
import json

from fastapi.responses import StreamingResponse

from utils import make_id, utcnow  # noqa: F401 — re-export for router modules


def sse_event(event_type: str, **data) -> str:
    """构建 SSE 事件字符串。
    
    用法: yield sse_event("token", token="你好")  
    等价于: yield f"data: {json.dumps({'type': 'token', 'token': '你好'}, ensure_ascii=False)}\n\n"
    """
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_response(generator):
    """包装生成器为 StreamingResponse，统一 SSE 头。
    
    用法: return sse_response(generate())
    """
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
