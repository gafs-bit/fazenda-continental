# Asking the system questions

The farm data is queryable through Claude Code once the `gbrain` MCP server is
connected (see main `README.md` for the pipeline that gets data into gbrain in
the first place). This doc is about the other side: how to ask questions so
you actually get answers grounded in the real data.

## How an answer actually gets made

```
1. You ask a question (in a Claude Code session with gbrain connected)
        ↓
2. Claude recognizes it needs farm data and calls the gbrain tool
        ↓
3. gbrain turns your question into a "meaning vector" (via ZeroEntropy)
        ↓
4. gbrain compares it against every stored record's vector (semantic search)
   + does a plain keyword search in parallel, blends both rankings
        ↓
5. gbrain returns the top-ranked matching records (raw text, not an answer)
        ↓
6. Claude reads those records and writes the actual answer
```

gbrain is the search engine; Claude is what writes the sentence. This pattern
is called RAG (Retrieval-Augmented Generation) — the answer is grounded in
retrieved records, not generated purely from the model's own training.

## Good practices to make sure it actually searches the data

**1. Name the tool explicitly when it matters.** Say "search gbrain for..."
or "use the gbrain tool to find..." instead of just asking bare. This is the
single most reliable way to trigger an actual tool call.

**2. Phrase questions so they clearly need a lookup, not general knowledge.**
- Good: *"What does our data show for sorghum loads in June?"*
- Risky: *"How do sorghum weighings usually work?"* — sounds like general
  agronomy knowledge, might get answered without touching gbrain at all.

Anchor the question to something only the real data could answer — a date
range, a specific field name, a romaneio number, a driver name.

**3. Ask for specifics that can't be guessed.** Exact weights, dates,
percentages, or IDs force retrieval, since there's no plausible way to answer
convincingly without actually looking. Vague/summary questions are the ones
most likely to get an ungrounded-but-confident-sounding answer.

**4. Verify at the start of a session.** Run `/mcp` right after opening a new
Claude Code session and confirm `gbrain` shows as connected before relying on
it. New MCP servers only load at session start — they can't be picked up
mid-conversation.

**5. Ask for sources when in doubt.** If an answer feels off or too smooth,
ask "which gbrain pages did you pull that from?" or "show me the romaneio
numbers." If Claude can't cite specific records, it likely didn't actually
search.

**6. Watch for "recalled memories" instead of a tool call.** Claude Code has
its own separate memory system (notes carried across conversations),
independent of gbrain. An answer that mentions recalling memories with no
tool call is answering from a cached summary of past conversations, not
fresh data — worth catching, since memory can go stale.

## Known limitation: no SQL fallback, but it's not bulletproof

`CLAUDE.md` in this repo bans direct SQL/psql against `pesagens` /
`fretes_colheita` unconditionally — even for exact counts/totals/exhaustive
searches, gbrain should be pushed harder (raised search limit, multiple
queries) rather than bypassed. This is a **prose rule**, not a technical
guardrail — it has been bypassed twice before being hardened to this
unconditional form, and there's no enforced permission block behind it yet.
If you notice SQL being used instead of gbrain, that's worth reporting; the
next step discussed (not yet implemented) is a `settings.json` deny rule
blocking Bash access to `psql`/`gbrain_dev` in this project.
