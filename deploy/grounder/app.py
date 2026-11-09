"""Docker entrypoint for Qwen3-VL-4B inference only.

This service deliberately contains no LoRA, GRPO, optimizer, dataset, or
training code.  A separately trained checkpoint can be selected with MODEL_ID
and MODEL_REVISION.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator


class Candidate(BaseModel):
    home_id: str
    device_id: str
    room_id: str | None = None
    capability: str | None = None
    name: str
    aliases: list[str] = Field(default_factory=list)


class GroundRequest(BaseModel):
    image_uri: str
    query: str
    candidates: list[Candidate]
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("image_uri")
    @classmethod
    def validate_image_uri(cls, value: str) -> str:
        if len(value) > 20 * 1024 * 1024:
            raise ValueError("image_uri payload exceeds 20 MiB")
        if value.startswith("data:image/"):
            return value
        parsed = urlparse(value)
        if parsed.scheme == "file":
            allowed_root = os.path.realpath(os.getenv("IMAGE_ROOT", "/data/images"))
            target = os.path.realpath(parsed.path)
            if target == allowed_root or target.startswith(allowed_root + os.sep):
                return value
            raise ValueError("file image_uri is outside IMAGE_ROOT")
        allowed_hosts = {
            host.strip().lower()
            for host in os.getenv("ALLOWED_IMAGE_HOSTS", "").split(",")
            if host.strip()
        }
        if parsed.scheme == "https" and parsed.hostname and parsed.hostname.lower() in allowed_hosts:
            return value
        raise ValueError("image_uri scheme or host is not allowed")


class BatchGroundRequest(BaseModel):
    requests: list[GroundRequest] = Field(min_length=1, max_length=16)


class Engine:
    def __init__(self) -> None:
        self.model_id = os.getenv("MODEL_ID", "Qwen/Qwen3-VL-4B-Instruct")
        self.revision = os.getenv("MODEL_REVISION", "main")
        self.max_new_tokens = int(os.getenv("MAX_NEW_TOKENS", "512"))
        self.model = None
        self.processor = None
        self.lock = threading.Lock()
        self.load_error = ""

    def load(self) -> None:
        if self.model is not None:
            return
        with self.lock:
            if self.model is not None:
                return
            try:
                import torch
                from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

                self.processor = AutoProcessor.from_pretrained(
                    self.model_id, revision=self.revision, trust_remote_code=False
                )
                self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                    self.model_id,
                    revision=self.revision,
                    torch_dtype=torch.bfloat16,
                    device_map="auto",
                    trust_remote_code=False,
                ).eval()
            except Exception as exc:
                self.load_error = f"{type(exc).__name__}: {exc}"
                raise

    def ground(self, request: GroundRequest) -> dict[str, Any]:
        self.load()
        candidate_payload = [candidate.model_dump() for candidate in request.candidates]
        instruction = (
            "You are a smart-home visual grounding tool. Select only from the supplied "
            "candidate device_ids. Return strict JSON with keys selected_device_id, "
            "ambiguous, candidates. Each candidate item has device_id, normalized bbox "
            "[x1,y1,x2,y2], score in [0,1], and short evidence. If evidence is insufficient, "
            "set selected_device_id to null and ambiguous to true.\n"
            f"User reference: {request.query}\n"
            f"Candidates: {json.dumps(candidate_payload, ensure_ascii=False)}"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": request.image_uri},
                    {"type": "text", "text": instruction},
                ],
            }
        ]
        inputs = self.processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)
        with self.lock:
            generated = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        trimmed = generated[:, inputs["input_ids"].shape[1] :]
        text = self.processor.batch_decode(trimmed, skip_special_tokens=True)[0]
        parsed = self._extract_json(text)
        allowed = {candidate.device_id for candidate in request.candidates}
        selected = parsed.get("selected_device_id")
        if selected is not None and selected not in allowed:
            raise ValueError("model selected a device outside the anchored candidate set")
        normalized = []
        for item in parsed.get("candidates", [])[: request.top_k]:
            if item.get("device_id") not in allowed:
                continue
            bbox = [float(value) for value in item.get("bbox", [])]
            if len(bbox) != 4:
                bbox = None
            elif max(bbox) > 1.0:
                bbox = [max(0.0, min(value / 1000.0, 1.0)) for value in bbox]
            normalized.append(
                {
                    "device_id": item["device_id"],
                    "bbox": bbox,
                    "score": max(0.0, min(float(item.get("score", 0.0)), 1.0)),
                    "evidence": str(item.get("evidence", ""))[:500],
                }
            )
        return {
            "selected_device_id": selected,
            "ambiguous": bool(parsed.get("ambiguous", selected is None)),
            "candidates": normalized,
            "model_version": f"{self.model_id}@{self.revision}",
        }

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        candidate = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
        if not candidate:
            raise ValueError("model did not return JSON")
        return json.loads(candidate)


engine = Engine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    thread = threading.Thread(target=_load_model, name="grounder-model-loader", daemon=True)
    thread.start()
    yield


def _load_model() -> None:
    try:
        engine.load()
    except Exception:
        # Engine records the redacted error for the readiness endpoint.
        return


app = FastAPI(
    title="HomeClaw Qwen3-VL Grounder",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, Any]:
    if engine.load_error:
        raise HTTPException(status_code=503, detail="model load failed")
    if engine.model is None:
        raise HTTPException(status_code=503, detail="model is loading")
    return {
        "status": "ready",
        "model_id": engine.model_id,
        "revision": engine.revision,
    }


@app.post("/v1/ground")
def ground(request: GroundRequest) -> dict[str, Any]:
    if not request.candidates:
        raise HTTPException(status_code=422, detail="anchored candidates are required")
    started = time.perf_counter()
    try:
        result = engine.ground(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"grounder unavailable: {type(exc).__name__}") from exc
    result["latency_ms"] = (time.perf_counter() - started) * 1000.0
    return result


@app.post("/v1/ground:batch")
def ground_batch(batch: BatchGroundRequest) -> dict[str, Any]:
    started = time.perf_counter()
    results = []
    for request in batch.requests:
        try:
            result = engine.ground(request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"grounder unavailable: {type(exc).__name__}"
            ) from exc
        results.append(result)
    return {
        "results": results,
        "batch_size": len(results),
        "latency_ms": (time.perf_counter() - started) * 1000.0,
    }
