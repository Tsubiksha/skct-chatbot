import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from backend.auth import get_current_user
from backend.database import (
    create_conversation,
    get_conversations_by_user,
    get_conversation,
    delete_conversation,
    add_message,
    get_messages
)
from backend.app.graph_sqlite.answer_service import answer_graph_question as _answer_fn

# Shim: wrap sync answer_graph_question as async for compatibility with existing route
async def graph_rag_query(question: str) -> dict:
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(None, _answer_fn, question)

router = APIRouter(tags=["Chat Operations"])

class CreateConversationRequest(BaseModel):
    title: str = "New Chat"

class MessagePostRequest(BaseModel):
    content: str

@router.post("/conversations")
async def create_new_conversation(
    req: CreateConversationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    try:
        conv_id = create_conversation(current_user["id"], req.title)
        conv = get_conversation(conv_id, current_user["id"])
        return conv
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}")

@router.get("/conversations")
async def list_conversations(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    try:
        convs = get_conversations_by_user(current_user["id"])
        return convs
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list conversations: {str(e)}")

@router.delete("/conversations/{conv_id}")
async def delete_user_conversation(
    conv_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    success = delete_conversation(conv_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or unauthorized")
    return {"success": True}

@router.get("/conversations/{conv_id}/messages")
async def get_conversation_messages(
    conv_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    # Verify ownership
    conv = get_conversation(conv_id, current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or unauthorized")
    
    messages = get_messages(conv_id)
    return messages

@router.post("/conversations/{conv_id}/messages")
async def stream_assistant_message(
    conv_id: int,
    req: MessagePostRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    # Verify ownership of the conversation
    conv = get_conversation(conv_id, current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found or unauthorized")
    
    message_content = req.content
    if not message_content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    async def event_generator():
        try:
            result = await graph_rag_query(message_content)
            cleaned_citations = [_format_source(source) for source in result.get("sources", [])]
            cleaned_graph = [_format_graph_row(row) for row in result.get("graph_context", [])]

            yield f"data: {json.dumps({'type': 'citations', 'citations': cleaned_citations})}\n\n"
            yield f"data: {json.dumps({'type': 'graph', 'graph': cleaned_graph})}\n\n"

            complete_text = result.get("answer") or "I could not find this information in the SKCT website data."
            for token in _stream_text_chunks(complete_text):
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

            add_message(conv_id, "user", message_content)
            add_message(
                conv_id, 
                "assistant", 
                complete_text, 
                sources=cleaned_citations, 
                graph_context=cleaned_graph
            )
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            err_msg = f"[System Error during stream: {str(e)}]"
            yield f"data: {json.dumps({'type': 'token', 'text': err_msg})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _format_source(source: Dict[str, Any]) -> Dict[str, Any]:
    lowered_text = (source.get("chunk_text") or source.get("snippet") or "").lower()
    dept_tag = "General"
    for full_name, keywords in {
        "CSE": ["cse", "computer science", "computer engineering"],
        "AIDS": ["aids", "ai & ds", "ai and ds", "artificial intelligence"],
        "ECE": ["ece", "electronics and communication"],
        "EEE": ["eee", "electrical and electronics"],
        "IT": ["it", "information technology"],
        "Civil": ["civil engineering", "civil"],
        "Mechanical": ["mechanical engineering", "mechanical"],
    }.items():
        if any(keyword in lowered_text for keyword in keywords):
            dept_tag = full_name
            break

    raw_score = source.get("score", source.get("confidence", 0))
    try:
        numeric_score = float(raw_score)
        score = int(numeric_score * 100) if numeric_score <= 1 else int(numeric_score)
    except (TypeError, ValueError):
        score = 0

    return {
        "title": source.get("title", "SKCT Website Page"),
        "url": source.get("url", "https://skct.edu.in"),
        "score": max(0, min(100, score)),
        "rank": source.get("rank"),
        "supporting_chunks": source.get("supporting_chunks", 1),
        "department": dept_tag,
        "snippet": (source.get("chunk_text") or source.get("snippet") or "")[:400],
    }


def _format_graph_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_name": row.get("source_name"),
        "relationship_type": row.get("relationship_type"),
        "target_name": row.get("target_name"),
    }


def _stream_text_chunks(text: str, chunk_size: int = 80):
    for index in range(0, len(text), chunk_size):
        yield text[index:index + chunk_size]
