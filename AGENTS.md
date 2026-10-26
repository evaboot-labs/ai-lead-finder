# Agent instructions

This repo is an AI lead finder. The user describes the leads they want in one sentence. The agent builds the Sales Navigator search with Evaboot, previews it for free, judges every previewed lead against `TARGET.md`, tightens the search until it reaches the precision target, exports the leads with verified emails, and offers a weekly recurring export. When the user asks to find leads, generate leads with AI, or build a lead list:

1. Follow the skill in `skills/ai-lead-finder/SKILL.md` step by step.
2. Read `TARGET.md` for what fits, what does not, and the precision target. If it says `Status: EXAMPLE`, ask the user and update it.
3. Use `finder.py` to score the rounds, report on the export and write the CSV. The Evaboot MCP server does the Sales Navigator work (`.mcp.json`).
4. If the user is not connected yet, follow `docs/connect-your-agent.md` with them.
5. If the user wants n8n instead, follow `docs/n8n.md` with them one step at a time: you cannot click inside n8n, so say exactly what to do and wait for their confirmation.

Previews are free; exports cost 1 Evaboot credit per lead. Confirm with the user before every export and before creating a recurring export. Never ask for or handle an API key: the user writes it into `.env`. Never commit `.env` or `data/`: they hold real people's data.
