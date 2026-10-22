# Run it in n8n

[`n8n/ai-lead-finder.json`](../n8n/ai-lead-finder.json) is the same lead finder for n8n. You describe your leads in a form, Claude judges a free preview, and you decide before any credit is spent.

## What runs

1. **Describe your leads** (form): one sentence (roles, seniority, country), the company size, the industry, the title words to exclude, and how many leads to export.
2. **Build the search** (MCP Client): Evaboot turns the sentence into a Sales Navigator search, then **Check the build** waits until it is ready.
3. **Add size, industry and exclusions** (Code): adds those filters to the URL. Asking the builder for them instead starts a slow company-first crawl.
4. **Preview 25 leads (free)** (MCP Client), then **Judge the preview** (AI Agent with Claude): fit or not, with a reason, for each lead.
5. **Precision** (Code) and **Review the search** (form page): the result count, the share that fits, what still gets through, and the search link. Export, or stop and submit the form again with a tighter description.
6. **Export with Evaboot** (1 credit per lead), **Lead rows** and **Add to your sheet**.
7. **Every week?** (form page): on a yes, **Create the weekly export** schedules the search; each run returns only new people.

## Set it up

1. **Make the sheet:** a Google Sheet with this header row:
   `First Name, Last Name, Current Job, Company Name, Company Domain, Email, Email Status, Company Employee Range, Company Industry, Location, Linkedin URL Public`
2. **Import** the JSON in n8n: *Workflows > Import from file*.
3. **Add three credentials:**
   - **Bearer Auth** named `Evaboot MCP (Bearer)`: your key from [dash.evaboot.com/dash/api/](https://dash.evaboot.com/dash/api/). Select it on every MCP Client node.
   - **Anthropic** on the Claude node.
   - **Google Sheets** on **Add to your sheet**.
4. **Fill in Your settings:** `sheet_url` (with its `gid`) and `target_precision` (0.8 means 20 of 25 previewed leads must fit).
5. **Publish** the workflow and open the form's production URL.
6. **Test:** describe your leads, ask for 5, read the review page, export, and answer No to the weekly question the first time.

## Good to know

- The industry list in the form holds common LinkedIn industries. To add one, copy its id from a Sales Navigator URL that filters on it and add it to `INDUSTRIES` in `n8n/build_workflow.py` (or to the Code node).
- A weekly run spends credits for each new lead. To send each run to your sheet or CRM, connect a destination in Evaboot's Integrations page and attach the recurring export to it.

Back to the [README](../README.md).
