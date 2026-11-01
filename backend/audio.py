"""Realtime transcription relay and Live WebRTC signaling. API keys stay server-side."""

import asyncio
import base64
import contextlib
import os
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, Field

import services as svc
from backend.domain import StrictModel, days_left
from backend.config import trusted_origins, local_today
from backend.llm import get_provider, make_plan, parse_items


class Offer(BaseModel):
    sdp: str = Field(min_length=1, max_length=64000)


class DelegateIn(BaseModel):
    transcript: str = Field(min_length=1, max_length=12000)


class Intent(StrictModel):
    action: Literal[
        "groceries",
        "household_add",
        "household_lookup",
        "plan",
        "research_plan",
        "pantry",
        "clarify",
    ]
    clarification: str | None
    language: Literal["english", "hindi", "hinglish"] = "english"


def create_router(auth_dependency):
    router = APIRouter()

    @router.websocket("/api/voice/stream")
    async def stream(ws: WebSocket):
        origin = ws.headers.get("origin")
        if not origin or origin.rstrip("/") not in trusted_origins():
            await ws.close(code=1008)
            return
        token = ws.cookies.get("sx_at")
        try:
            user = (
                await asyncio.to_thread(lambda: svc.get_db().auth.get_user(token).user)
                if token
                else None
            )
        except Exception:
            user = None
        if not user:
            await ws.close(code=1008)
            return
        await ws.accept()
        tasks = []
        try:
            async with AsyncOpenAI(timeout=20, max_retries=0) as client:
                async with client.realtime.connect(
                    extra_query={"intent": "transcription"}, max_retries=0
                ) as connection:
                    await connection.send(
                        {
                            "type": "session.update",
                            "session": {
                                "type": "transcription",
                                "audio": {
                                    "input": {
                                        "format": {"type": "audio/pcm", "rate": 24000},
                                        "transcription": {
                                            "model": "gpt-live-transcribe",
                                            "prompt": "Groceries and household items, including Hindi and English code-switching: doodh, milk, sabzi, chawal, do din, kal, fridge.",
                                            "languages": ["en", "hi"],
                                        },
                                        "turn_detection": None,
                                    }
                                },
                            },
                        }
                    )

                    async def from_browser():
                        total_bytes = 0
                        while True:
                            event = await asyncio.wait_for(
                                ws.receive_json(), timeout=90
                            )
                            kind = event.get("type")
                            if kind == "audio":
                                audio = event.get("audio", "")
                                if len(audio) > 65536:
                                    raise ValueError("Audio chunk too large")
                                raw = base64.b64decode(audio, validate=True)
                                if len(raw) % 2:
                                    raise ValueError("PCM16 requires complete samples")
                                total_bytes += len(raw)
                                if total_bytes > 24000 * 2 * 120:
                                    raise ValueError(
                                        "Maximum recording length is two minutes"
                                    )
                                await connection.input_audio_buffer.append(audio=audio)
                            elif kind == "commit":
                                if total_bytes < 4800:
                                    raise ValueError(
                                        "Record at least 100 ms before stopping"
                                    )
                                await connection.input_audio_buffer.commit()
                            else:
                                raise ValueError("Unsupported audio command")

                    async def to_browser():
                        async for event in connection:
                            payload = event.model_dump(mode="json")
                            if event.type == "session.updated":
                                await ws.send_json({"type": "ready"})
                            elif event.type in {
                                "conversation.item.input_audio_transcription.delta",
                                "conversation.item.input_audio_transcription.completed",
                                "conversation.item.input_audio_transcription.failed",
                                "error",
                            }:
                                await ws.send_json(payload)
                                if event.type.endswith(".completed"):
                                    return

                    tasks = [
                        asyncio.create_task(from_browser()),
                        asyncio.create_task(to_browser()),
                    ]
                    done, _ = await asyncio.wait(
                        tasks, timeout=150, return_when=asyncio.FIRST_COMPLETED
                    )
                    if not done:
                        raise TimeoutError()
                    for task in done:
                        task.result()
        except WebSocketDisconnect:
            pass
        except Exception:
            with contextlib.suppress(Exception):
                await ws.send_json(
                    {
                        "type": "error",
                        "error": {
                            "message": "Realtime connection failed. Check microphone, account access and network, then retry or enter text."
                        },
                    }
                )
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            with contextlib.suppress(Exception):
                await ws.close()

    @router.post("/api/live/session", status_code=201)
    async def live_session(body: Offer, ctx=Depends(auth_dependency)):
        if os.getenv("LIVE_ENABLED", "true").lower() != "true":
            raise HTTPException(
                503, "Set LIVE_ENABLED=true to enable browser Live conversations."
            )
        try:
            async with AsyncOpenAI(timeout=25, max_retries=0) as client:
                # SDK 2.54 lacks the typed Live resource. Generic SDK HTTP sends the documented API request.
                return await client.post(
                    "/live/sessions",
                    cast_to=dict[str, object],
                    body={
                        "session": {
                            "model": "gpt-live-1",
                            "instructions": "You are SaveX, a concise household assistant. Understand Hindi, English, and Hinglish and reply in the user’s language. Delegate grocery items (including doodh, sabzi, and milk), household items, pantry questions, and meal requests to the backend. Ask for missing details and direct the user to review proposals on screen. Never claim items were saved before the user confirms. Never invent dates, quantities, locations or shelf life.",
                            "delegation": {"type": "client"},
                        },
                        "transport": {"type": "webrtc", "sdp": body.sdp},
                    },
                )
        except APIError:
            raise HTTPException(
                502,
                "Live session could not be created. Verify model access and network.",
            )

    @router.post("/api/live/delegate")
    def delegate(body: DelegateIn, ctx=Depends(auth_dependency)):
        try:
            intent = get_provider().generate(
                "Set language to english, hindi or hinglish based on the user. Hinglish mixes English with Romanized Hindi: doodh, leke aaya, do din, kharab ho jaayega and fata fat are Hinglish even with English greetings. Classify the latest user request. Food and drinks always count as groceries, including doodh/दूध (milk, sometimes mis-transcribed as दूद or दूँद), sabzi, dal, chawal, atta, eggs and bread. For example, doodh leke aaya tha, do din mein kharab ho jaayega is groceries with language hinglish, not household_add. Use household_add only for nonfood household objects, household_lookup for object location, plan for meals, research_plan for web recipe research, pantry for food inventory, clarify if unclear. Never execute mutations.",
                {"conversation": body.transcript},
                Intent,
            )
            if intent.action == "groceries":
                items = parse_items(body.transcript, local_today())
                if not items:
                    return {
                        "kind": "clarify",
                        "commentary": "Mujhe item samajh nahi aaya. Kya aap item aur expiry details dobara bata sakte hain?",
                    }
                missing = any(
                    not i.get("bought_date")
                    or i.get("shelf_days") is None
                    or not i.get("location")
                    for i in items
                )
                if intent.language in {"hindi", "hinglish"}:
                    commentary = (
                        "Item screen par hai. Jo details missing hain, bhar kar Confirm dabaiye. Abhi save nahi hua."
                        if missing
                        else "Items screen par hain. Check karke Confirm dabaiye; tabhi save honge."
                    )
                else:
                    commentary = (
                        "Review the item on screen, fill in any missing details, and press Confirm. Nothing has been saved yet."
                        if missing
                        else "Review the items and press Confirm to save them."
                    )
                return {"kind": "groceries", "items": items, "commentary": commentary}
            if intent.action == "household_add":
                from backend.household import extract_household

                items = extract_household(body.transcript)
                return {
                    "kind": "household",
                    "items": items,
                    "commentary": "Household proposals are shown on screen. Check the category and location, then confirm to save. Nothing has been saved.",
                }
            if intent.action == "household_lookup":
                items = (
                    ctx.db.table("household_items")
                    .select("name,category,location,recorded_at")
                    .order("recorded_at", desc=True)
                    .limit(50)
                    .execute()
                    .data
                )
                return {
                    "kind": "household_lookup",
                    "commentary": str(items)
                    if items
                    else "There are no household items recorded.",
                }
            if intent.action == "research_plan":
                from backend.research import search_recipes, search_meal_images
                from backend.domain import inventory_context

                items = (
                    ctx.db.table("items")
                    .select("*")
                    .eq("status", "active")
                    .execute()
                    .data
                )
                active, priority = inventory_context(items, local_today())
                if not active:
                    return {
                        "kind": "clarify",
                        "commentary": "Add food items before planning meals.",
                    }
                sources = search_recipes(priority or [item["name"] for item in active])
                plan = {
                    **make_plan(active, local_today(), research=sources),
                    "sources": sources,
                }
                plan["meal_images"] = search_meal_images(plan["meals"])
                return {"kind": "plan", "plan": plan, "commentary": str(plan["meals"])}
            if intent.action == "plan":
                items = (
                    ctx.db.table("items")
                    .select("*")
                    .eq("status", "active")
                    .execute()
                    .data
                )
                plan = make_plan(items, local_today())
                return {"kind": "plan", "plan": plan, "commentary": str(plan)}
            if intent.action == "pantry":
                items = (
                    ctx.db.table("items")
                    .select("name,expiry_date,location,status")
                    .eq("status", "active")
                    .order("expiry_date")
                    .execute()
                    .data
                )
                usable = [i for i in items if days_left(i, local_today()) >= 0]
                return {
                    "kind": "pantry",
                    "commentary": str(usable)
                    if usable
                    else "The active pantry is empty.",
                }
            return {
                "kind": "clarify",
                "commentary": intent.clarification
                or "Would you like to add groceries, review your pantry, or plan meals?",
            }
        except Exception:
            logging.getLogger("savex").exception("Live voice delegation failed")
            raise HTTPException(
                502, "Voice task failed. Your pantry has not been changed."
            )

    return router
