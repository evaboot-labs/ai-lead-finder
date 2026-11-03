---
name: ai-lead-finder
description: Find B2B leads with AI from one sentence - build the Sales Navigator search through Evaboot, preview 25 sample leads for free from the search builder, judge each against TARGET.md, tighten the search until it reaches the precision target, export the leads with verified emails, report on them, and set a weekly recurring export that returns only new people. Use when the user asks to generate leads with AI, find leads, build a lead list, or turn an ICP into a Sales Navigator search.
---

# AI lead finder

This skill runs inside a clone of https://github.com/evaboot-labs/ai-lead-finder: it uses the repo's `finder.py`, `TARGET.md` and `docs/`. If `finder.py` is not in the working directory, clone the repo and work from there.

You do the Sales Navigator and Evaboot work through the Evaboot MCP server (`https://mcp.evaboot.com/mcp`). Every tool named below is an Evaboot MCP tool. You judge the previews yourself. `finder.py` scores your rounds, reports on the export and writes the CSV.

## Rules

- **Previews are free; exports are not.** Never export before the last preview reaches the precision target in `TARGET.md`, unless the user says so.
- Confirm with the user before `export_sn_search_or_list` and `create_recurring_export`. Show the count and the cost (1 Evaboot credit per exported lead), then wait for a yes.
- Judge each previewed lead from its title and company only, and write a reason for every lead that does not fit. Never guess facts you cannot see.
- Never ask for or paste an API key. The user writes `EVABOOT_API_KEY` into `.env` and exports it in the shell before starting the agent (`docs/connect-your-agent.md`): `.mcp.json` reads it from the environment.
- Print every Sales Navigator URL as a Markdown link with the URL in angle brackets: `[Open in Sales Navigator](<url>)`.

## Step 0: check the setup

1. If the Evaboot MCP tools are not in this session, walk the user through `docs/connect-your-agent.md`, then ask them to restart the agent from this folder.
2. Otherwise call `verify_token` and `get_daily_export_quota`. If `has_valid_salesnav` is false, ask the user to sign in to Evaboot in Chrome, open any Sales Navigator search with the Evaboot extension, and click Export with Evaboot, then call the quota again.
3. Run `mkdir -p data` and `cp .env.example .env` if `.env` is missing.
4. Read `TARGET.md`. If it says `Status: EXAMPLE`, use the sentence the user already gave you and ask only for what is missing: what fits, what does not, and how many leads per run. Rewrite the file and set `Status: yours`.

## Step 1: round 1, the sentence

1. Call `build_sn_search_from_prompt` with **the people part only**: roles, seniority and place, and end the prompt with "Show me 25 sample people in your reply." Leave the industry out: naming a vertical starts a slow company-first crawl that writes account lists on the user's seat. Pass `max_results` = the leads per run. Poll `get_search_build` until `status` is `complete`.
2. The finished build is the free preview: `result_count` is the total, and `reply` holds a table of sample people (name, title, company). Check `strategy` is `leads`; if it is account-based, stop and tell the user before anything else runs. Keep the `conversation_id` for the next rounds.
3. Judge every person in the table (`finder.py` needs at least 20; if the reply shows fewer, ask the builder again in the same conversation for 25 sample people): `fit` true or false, and a short `reason` for each miss, with the same wording for the same kind of miss. Add the round to `data/rounds.json`: `{"round", "change", "url", "total", "sample": [{"title", "company", "fit", "reason"}]}`.

```bash
python3 finder.py rounds data/rounds.json
```

## Step 2: tighten, up to round 3

Read the misses `finder.py` lists, change one thing, and preview again: call `build_sn_search_from_prompt` with the same `conversation_id`, name the one change, say "keep everything else", and ask again for 25 sample people. Then judge the new table and add the round. Never edit the URL by hand between rounds: a hand-edited URL has no free preview.

- **Company size:** ask for the Company headcount filter by range (for example 51-200 and 201-500) on the same people search. It stays a lead search.
- **Industry:** do not ask the builder for it, it starts the company-first crawl. Judge the industry from the company names in the preview, and check it again on the export, which carries each company's industry.
- **Wrong roles:** ask to exclude the words that keep coming back (Consultant, Advisor, Fractional...) from the job title. Never exclude a phrase that is part of a good title: "Director of Sales" also removes "Director of Sales Operations".
- After each round, read `filters_used`: confirm the builder made your one change and nothing else, and undo any filter you did not ask for.

Stop when `finder.py rounds` says `ready to export`, or after round 3: then show the user the misses and ask.

## Step 3: export and report

1. On a yes, call `export_sn_search_or_list` with the last URL and `max_results`, and poll `get_export` with `limit: 0` until `EXECUTED`.
2. Save the leads: `set -a; . ./.env; set +a; curl -s -H "Authorization: Bearer $EVABOOT_API_KEY" https://api.evaboot.com/v1/extractions/<extraction_id>/ > data/export.json`
3. Report and write the CSV:

```bash
python3 finder.py report data/export.json
python3 finder.py csv data/export.json --seen data/seen.txt > data/leads-$(date +%F).csv
```

Tell the user how many leads have a `safe` email: only those are ready for outreach.

## Step 4: every week

Offer `create_recurring_export` on the export's `extraction_id` (weekly). Each run returns only the people who are new to the search, so you never pay twice for the same person. Each run spends credits; say so before creating it. Then ask where the leads should land: `list_integrations`, then `attach_recurring_export`, or `connect_integration` for a new Google Sheet, CRM or outreach tool. To process a run by hand instead, find it with `get_export_list`, save it as in step 3, and run `finder.py csv --seen` on it: only new people come out.
