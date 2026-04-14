from __future__ import annotations

from typing import Any

import httpx


def build_grounded_prompt(question: str, contexts: list[dict[str, Any]]) -> str:
    context_lines: list[str] = []
    for index, item in enumerate(contexts, start=1):
        citation_id = f"C{index}"
        source = item.get("source_file", "unknown")
        chunk_index = item.get("chunk_index", "unknown")
        page_range = item.get("page_range") or "n/a"
        section_title = item.get("section_title") or "n/a"
        chunk_text = item.get("chunk_text", "")
        context_lines.append(
            "\n".join(
                [
                    f"[{citation_id}] source_file={source}",
                    f"[{citation_id}] chunk_index={chunk_index}",
                    f"[{citation_id}] page_range={page_range}",
                    f"[{citation_id}] section_title={section_title}",
                    f"[{citation_id}] text={chunk_text}",
                ]
            )
        )

    context_block = "\n\n".join(context_lines)
    return (
        "You are a legal assistant. Answer using only the provided context.\n"
        "Rules:\n"
        "1) Do not use outside knowledge.\n"
        "2) If at least one context chunk clearly answers the question, answer directly and cite it.\n"
        "3) If context is insufficient, say exactly: Insufficient evidence in provided documents.\n"
        "4) Include inline citations like [C1], [C2] for every key claim.\n"
        "5) Keep answer concise and factual.\n\n"
        f"Question:\n{question}\n\n"
        f"Context:\n{context_block}\n\n"
        "Return only the final answer text."
    )


def build_summary_prompt(source_file: str, contexts: list[dict[str, Any]]) -> str:
    context_lines: list[str] = []
    for index, item in enumerate(contexts, start=1):
        citation_id = f"C{index}"
        page_range = item.get("page_range") or "n/a"
        section_title = item.get("section_title") or "n/a"
        chunk_text = item.get("chunk_text", "")
        context_lines.append(
            "\n".join(
                [
                    f"[{citation_id}] page_range={page_range}",
                    f"[{citation_id}] section_title={section_title}",
                    f"[{citation_id}] text={chunk_text}",
                ]
            )
        )

    context_block = "\n\n".join(context_lines)
    return (
        "You are a legal assistant creating a concise grounded legal summary.\n"
        "Rules:\n"
        "1) Use only the provided context.\n"
        "2) Write 3-5 short numbered points (not bullets) in plain language.\n"
        "3) Each point must end with one or more inline citations like [C1], [C2].\n"
        "4) If context is insufficient, say exactly: Insufficient evidence in provided documents.\n\n"
        "5) Do not add legal conclusions beyond the provided context.\n"
        "6) Keep total output under 170 words.\n\n"
        f"Document: {source_file}\n\n"
        f"Context:\n{context_block}\n\n"
        "Return only the summary text."
    )


def generate_answer_with_ollama(
    *,
    base_url: str,
    model: str,
    prompt: str,
    timeout_seconds: float = 60.0,
) -> str:
    endpoint = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        body = response.json()

    answer_text = str(body.get("response", "")).strip()
    if not answer_text:
        raise RuntimeError("Ollama returned an empty response")
    return answer_text
