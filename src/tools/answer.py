import anthropic
import mcp.types as types
from src.store.search import hybrid_search

ANSWER_TOOL = types.Tool(
    name="answer_question",
    description=(
        "Answer a question using content from the personal knowledge base. "
        "Searches for relevant notes, then synthesises an answer with source citations. "
        "Use this when the user wants an answer, not just a list of results. "
        "Always cites which notes it drew from."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to answer",
            },
            "content_type": {
                "type": "string",
                "enum": ["video", "article", "note", "list", "doc"],
                "description": "Narrow search to a specific content type",
            },
            "source": {
                "type": "string",
                "description": "Narrow search to a specific source e.g. 'obsidian', 'inbox'",
            },
        },
        "required": ["question"],
    },
)


async def handle_answer(arguments: dict) -> list[types.TextContent]:
    question = arguments["question"]
    content_type = arguments.get("content_type")
    source = arguments.get("source")

    # a. Search for relevant chunks
    results = hybrid_search(question, content_type=content_type, source=source, limit=5)
    if not results:
        return [types.TextContent(
            type="text",
            text="I couldn't find anything in your knowledge base related to that question.",
        )]

    # b. Build context string
    context_parts = []
    for r in results:
        meta = r.get("metadata", {})
        title = meta.get("title") or r["note_id"]
        src = meta.get("source", "?")
        url = meta.get("url", "")
        excerpt = r.get("excerpt", "")
        block = f"[Source: {title} ({src})]\n{excerpt}"
        if url:
            block += f"\nURL: {url}"
        context_parts.append(block)
    context = "\n---\n".join(context_parts)

    # c. Build prompt
    system = (
        "You are a personal knowledge assistant. Answer the user's question using ONLY "
        "the provided context from their notes. Always cite which source you drew each "
        "point from using [Source: title]. If the context doesn't contain enough "
        "information to answer, say so clearly."
    )
    user_message = f"Context from my knowledge base:\n\n{context}\n\nQuestion: {question}"

    # d. Call Claude
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    answer = response.content[0].text

    # e. Format final response
    lines = [
        "Answer",
        "------",
        answer,
        "",
        "Sources used",
        "------------",
    ]
    for r in results:
        meta = r.get("metadata", {})
        title = meta.get("title") or r["note_id"]
        src = meta.get("source", "?")
        url = meta.get("url", "")
        lines.append(f"• {title} ({src}) — score: {r['rrf_score']}")
        if url:
            lines.append(f"  {url}")

    return [types.TextContent(type="text", text="\n".join(lines))]
