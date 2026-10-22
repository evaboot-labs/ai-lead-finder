"""Builds n8n/ai-lead-finder.json. Run: python3 n8n/build_workflow.py

A form takes one sentence (roles, seniority, country), the company size, the industry and the title words
to exclude. Evaboot builds the Sales Navigator search from the sentence, a Code node adds the size,
industry and exclusions to the URL, and a free preview of 25 leads goes to Claude, which judges each one.
A review page shows the result count and the precision; only on your yes does Evaboot export the leads
into your sheet. A last page offers a weekly recurring export that returns only new people.
"""
import json
import uuid
from pathlib import Path

MCP = "https://mcp.evaboot.com/mcp"
EVABOOT_CRED = {"httpBearerAuth": {"id": "", "name": "Evaboot MCP (Bearer)"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "", "name": "Anthropic"}}
SHEETS_CRED = {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets account"}}
MODEL = "claude-sonnet-5-5"
SIZES = {"11-50": "C", "51-200": "D", "201-500": "E", "501-1,000": "F", "1,001-5,000": "G"}
# LinkedIn industry ids. Add your own: the id is in any Sales Navigator URL that filters on that industry.
INDUSTRIES = {"Software Development": 4, "IT Services and IT Consulting": 96, "Financial Services": 43,
              "Staffing and Recruiting": 104, "Hospitals and Health Care": 14, "Advertising Services": 80,
              "Technology, Information and Internet": 6}

nodes, connections = [], {}


def node(name, type_, version, params, pos, creds=None, **extra):
    n = {"parameters": params, "id": str(uuid.uuid4()), "name": name, "type": type_,
         "typeVersion": version, "position": pos, **extra}
    if creds:
        n["credentials"] = creds
    nodes.append(n)


def link(a, b, kind="main", out=0):
    connections.setdefault(a, {}).setdefault(kind, [])
    while len(connections[a][kind]) <= out:
        connections[a][kind].append([])
    connections[a][kind][out].append({"node": b, "type": kind, "index": 0})


def mcp_call(name, tool, json_expr, pos):
    node(name, "@n8n/n8n-nodes-langchain.mcpClient", 1.1, {
        "endpointUrl": MCP, "authentication": "bearerAuth",
        "tool": {"__rl": True, "mode": "list", "value": tool, "cachedResultName": tool},
        "inputMode": "json", "jsonInput": json_expr, "options": {"timeout": 120000},
    }, pos, EVABOOT_CRED)


def code(name, js, pos, **extra):
    node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, pos, **extra)


def is_equal(name, left, right, pos):
    node(name, "n8n-nodes-base.if", 2.2, {"conditions": {
        "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
        "conditions": [{"id": str(uuid.uuid4()), "leftValue": left, "rightValue": right,
                        "operator": {"type": "string", "operation": "equals"}}],
        "combinator": "and"}, "options": {}}, pos)


FORM = "Describe your leads"

FILTERS_JS = r"""
// Add size, industry and title exclusions to the URL Evaboot built from the sentence. Asking the builder
// for them instead starts a slow company-first crawl.
const SIZES = __SIZES__, INDUSTRIES = __INDUSTRIES__;
const form = $('__FORM__').first().json;
let url = $json.structuredContent.result.url;
if (!url) throw new Error('Evaboot returned no search URL: ' + JSON.stringify($json.structuredContent.result).slice(0, 300));
const filters = [];
const sizes = (form['Company size'] || []).map(s => SIZES[s]).filter(Boolean);
if (sizes.length) filters.push(`(type%3ACOMPANY_HEADCOUNT%2Cvalues%3AList(${sizes.map(s => `(id%3A${s}%2CselectionType%3AINCLUDED)`).join('%2C')}))`);
const ind = INDUSTRIES[form['Industry']];
if (ind) filters.push(`(type%3AINDUSTRY%2Cvalues%3AList((id%3A${ind}%2CselectionType%3AINCLUDED)))`);
const words = String(form['Exclude these title words'] || '').split(',').map(w => w.trim()).filter(Boolean);
if (words.length) {
  const add = words.map(w => encodeURIComponent(encodeURIComponent(w.includes(' ') ? `"${w}"` : w))).join('%2520OR%2520');
  if (url.includes('%2520NOT%2520%2528')) url = url.replace(/%2529%2CselectionType%3AINCLUDED/, `%2520OR%2520${add}%2529%2CselectionType%3AINCLUDED`);
  else if (url.includes('CURRENT_TITLE')) url = url.replace(/(CURRENT_TITLE%2Cvalues%3AList\(\(text%3A[^,]*?)%2CselectionType/, `$1%2520NOT%2520%2528${add}%2529%2CselectionType`);
  else throw new Error('The search has no job title filter to exclude words from: describe the roles in the sentence.');
}
if (filters.length) {
  if (!/\)\)$/.test(url)) throw new Error('Unexpected search URL shape, filters not added: ' + url.slice(-80));
  url = url.replace(/\)\)$/, '%2C' + filters.join('%2C') + '))');
}
return [{ json: { url } }];
""".replace("__SIZES__", json.dumps(SIZES)).replace("__INDUSTRIES__", json.dumps(INDUSTRIES)).replace("__FORM__", FORM)

PRECISION_JS = r"""
// Same verdict as finder.py rounds: share of the previewed leads that fit, and what still gets through.
const target = Number($('Your settings').first().json.target_precision) || 0.8;
const verdicts = $json.output.leads || [];
if (verdicts.length < 20) throw new Error(`Claude judged ${verdicts.length} leads, at least 20 are needed. Run it again.`);
const fit = verdicts.filter(v => v.fit).length, n = verdicts.length || 1;
const misses = {};
verdicts.filter(v => !v.fit).forEach(v => { misses[v.reason] = (misses[v.reason] || 0) + 1; });
const preview = $('Preview 25 leads (free)').first().json.structuredContent.result.data;
return [{ json: {
  url: $('Add size, industry and exclusions').first().json.url, total: preview.paging.total,
  fit, judged: verdicts.length, precision: Math.round(100 * fit / n), ready: fit / n >= target,
  misses: Object.entries(misses).map(([r, c]) => `${c} x ${r}`).join('; ') || 'none',
} }];
"""

ROWS_JS = r"""
// One clean row per lead, the same columns as finder.py csv.
const p = $json.structuredContent.result.prospects || [];
if (!p.length) throw new Error('The export returned no leads.');
const cols = ['First Name', 'Last Name', 'Current Job', 'Company Name', 'Company Domain', 'Email', 'Email Status',
  'Company Employee Range', 'Company Industry', 'Location', 'Linkedin URL Public'];
return p.map(x => ({ json: Object.fromEntries(cols.map(c => [c, x[c] ?? ''])) }));
"""

JUDGE_SYSTEM = """You judge a Sales Navigator preview against what the user wants. For each lead in the JSON (title and company only), return {fit: true or false, reason}. A lead fits when its title matches the roles and seniority the user described and nothing in the title or company name contradicts the rest. Mark consultants, advisors, fractional and independent roles as not a fit. The reason is 2 to 6 words, the same wording for the same kind of miss. Never guess facts you cannot see.

What the user wants:
{{ $('""" + FORM + """').first().json['Who (roles, seniority, country)'] }}, company size {{ ($('""" + FORM + """').first().json['Company size'] || []).join(', ') || 'any' }}, industry {{ $('""" + FORM + """').first().json['Industry'] }}."""

node(FORM, "n8n-nodes-base.formTrigger", 2.2, {
    "formTitle": "Find leads with AI",
    "formDescription": "Describe the people you want in one sentence. Evaboot builds the Sales Navigator search, Claude judges a free preview of 25 leads, and you decide before any credit is spent.",
    "formFields": {"values": [
        {"fieldLabel": "Who (roles, seniority, country)", "fieldType": "textarea", "requiredField": True,
         "placeholder": "Heads, directors and VPs of Revenue Operations or Sales Operations in the United States"},
        {"fieldLabel": "Company size", "fieldType": "checkbox",
         "fieldOptions": {"values": [{"option": s} for s in SIZES]}},
        {"fieldLabel": "Industry", "fieldType": "dropdown",
         "fieldOptions": {"values": [{"option": "Any"}] + [{"option": i} for i in INDUSTRIES]}},
        {"fieldLabel": "Exclude these title words", "fieldType": "text",
         "placeholder": "Consultant, Advisor, Fractional, Independent"},
        {"fieldLabel": "Leads to export", "fieldType": "number", "requiredField": True, "placeholder": "20"},
    ]},
    "responseMode": "lastNode", "options": {},
}, [0, 0])
node("Your settings", "n8n-nodes-base.set", 3.4, {"assignments": {"assignments": [
    {"id": str(uuid.uuid4()), "name": "sheet_url", "type": "string", "value": "PASTE_YOUR_GOOGLE_SHEET_URL_WITH_GID"},
    {"id": str(uuid.uuid4()), "name": "target_precision", "type": "string", "value": "0.8"},
]}, "includeOtherFields": True, "options": {}}, [220, 0])
mcp_call("Build the search", "build_sn_search_from_prompt",
         f"={{{{ JSON.stringify({{ request: $('{FORM}').first().json['Who (roles, seniority, country)'], "
         f"max_results: Number($('{FORM}').first().json['Leads to export']) || 20 }}) }}}}", [440, 0])
node("Wait 20 s", "n8n-nodes-base.wait", 1.1, {"amount": 20}, [660, 0])
mcp_call("Check the build", "get_search_build",
         "={{ JSON.stringify({ build_id: $('Build the search').first().json.structuredContent.result.build_id }) }}",
         [880, 0])
is_equal("Built?", "={{ $json.structuredContent.result.status }}", "complete", [1100, 0])
code("Add size, industry and exclusions", FILTERS_JS, [1320, -100])
mcp_call("Preview 25 leads (free)", "search_sn_leads",
         "={{ JSON.stringify({ search_url: $json.url, count: 25 }) }}", [1540, -100])
node("Judge the preview", "@n8n/n8n-nodes-langchain.agent", 2.2, {
    "promptType": "define", "hasOutputParser": True,
    "text": "={{ JSON.stringify($json.structuredContent.result.data.elements.map(e => ({ title: e.title, company: e.company }))) }}",
    "options": {"systemMessage": "=" + JUDGE_SYSTEM, "maxIterations": 3},
}, [1760, -100], retryOnFail=True, maxTries=3, waitBetweenTries=2000)
node("Claude", "@n8n/n8n-nodes-langchain.lmChatAnthropic", 1.3, {
    "model": {"__rl": True, "mode": "list", "value": MODEL, "cachedResultName": MODEL},
    "options": {"maxTokensToSample": 4000},
}, [1720, 120], ANTHROPIC_CRED)
node("Verdicts", "@n8n/n8n-nodes-langchain.outputParserStructured", 1.3, {
    "schemaType": "manual",
    "inputSchema": json.dumps({"type": "object", "required": ["leads"], "properties": {"leads": {
        "type": "array", "items": {"type": "object", "required": ["fit", "reason"], "properties": {
            "fit": {"type": "boolean"}, "reason": {"type": "string"}}}}}}, indent=2),
}, [1880, 120])
code("Precision", PRECISION_JS, [1980, -100])
node("Review the search", "n8n-nodes-base.form", 2.3, {
    "formFields": {"values": [{"fieldLabel": "What next?", "fieldType": "dropdown", "requiredField": True,
                               "fieldOptions": {"values": [{"option": "Export the leads"}, {"option": "Stop here"}]}}]},
    "options": {"formTitle": "={{ $json.total.toLocaleString() }} people, {{ $json.precision }}% of the preview fits",
                "formDescription": "={{ $json.ready ? 'Ready to export.' : 'Under your target: tighten the sentence, the size, the industry or the excluded words, and submit the form again.' }} "
                                   "Still in the preview: {{ $json.misses }}. Exporting costs 1 Evaboot credit per lead "
                                   "({{ $('" + FORM + "').first().json['Leads to export'] }} leads). <a href=\"{{ $json.url }}\" target=\"_blank\">Open the search in Sales Navigator</a>"},
}, [2200, -100])
is_equal("Export?", "={{ $json['What next?'] }}", "Export the leads", [2420, -100])
mcp_call("Export with Evaboot", "export_sn_search_or_list",
         "={{ JSON.stringify({ linkedin_url: $('Precision').first().json.url, "
         f"max_results: Number($('{FORM}').first().json['Leads to export']) || 20, "
         "search_name: 'AI lead finder ' + $now.toFormat('yyyy-MM-dd') }) }}", [2640, -200])
node("Wait 30 s", "n8n-nodes-base.wait", 1.1, {"amount": 30}, [2860, -200])
mcp_call("Check the export", "get_export",
         "={{ JSON.stringify({ extraction_id: $('Export with Evaboot').first().json.structuredContent.result.extraction_id }) }}",
         [3080, -200])
is_equal("Done?", "={{ $json.structuredContent.result.status }}", "EXECUTED", [3300, -200])
code("Still running?", r"""
// Stop instead of waiting forever when the export failed.
const r = $json.structuredContent.result;
if (r.failure_reason || /FAIL|ERROR|CANCEL/i.test(r.status || '')) throw new Error(`The export stopped: ${r.status} ${r.failure_reason || ''}`);
return [$input.first()];
""", [3300, -40])
code("Lead rows", ROWS_JS, [3520, -300])
node("Add to your sheet", "n8n-nodes-base.googleSheets", 4.7, {
    "operation": "append",
    "documentId": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "sheetName": {"__rl": True, "mode": "url", "value": "={{ $('Your settings').first().json.sheet_url }}"},
    "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
    "options": {},
}, [3740, -300], SHEETS_CRED)
node("Every week?", "n8n-nodes-base.form", 2.3, {
    "formFields": {"values": [{"fieldLabel": "Repeat this search every week?", "fieldType": "dropdown", "requiredField": True,
                               "fieldOptions": {"values": [{"option": "Yes, every week"}, {"option": "No"}]}}]},
    "options": {"formTitle": "={{ $('Lead rows').all().length }} leads are in your sheet",
                "formDescription": "A weekly recurring export returns only the people who are new to this search, so you never pay twice for the same person. Each run spends 1 credit per new lead."},
}, [3960, -300], executeOnce=True)
is_equal("Weekly?", "={{ $json['Repeat this search every week?'] }}", "Yes, every week", [4180, -300])
mcp_call("Create the weekly export", "create_recurring_export",
         "={{ JSON.stringify({ extraction_id: $('Export with Evaboot').first().json.structuredContent.result.extraction_id, frequency: 'weekly' }) }}",
         [4400, -400])
node("Weekly export on", "n8n-nodes-base.form", 2.3, {
    "operation": "completion", "completionTitle": "Weekly export created",
    "completionMessage": "=Next run: {{ $json.structuredContent.result.next_execution_at.slice(0, 10) }}. "
                         "Connect a destination in Evaboot (Integrations) to send each run to your sheet or CRM.",
    "options": {}}, [4620, -400])
node("Leads saved", "n8n-nodes-base.form", 2.3, {"operation": "completion", "completionTitle": "Leads saved",
                                                 "completionMessage": "Your leads are in your sheet.", "options": {}},
     [4400, -200])
node("Stopped", "n8n-nodes-base.form", 2.3, {"operation": "completion", "completionTitle": "Nothing exported",
                                             "completionMessage": "No credit was spent. Submit the form again with a tighter description.",
                                             "options": {}}, [2640, 0])

# Two rows on the canvas: build, preview and judge on top; review, export and weekly below.
POS = {FORM: (0, 0), "Your settings": (220, 0), "Build the search": (440, 0), "Wait 20 s": (660, 0),
       "Check the build": (880, 0), "Built?": (1100, 0), "Add size, industry and exclusions": (1320, 0),
       "Preview 25 leads (free)": (1540, 0), "Judge the preview": (1780, 0), "Claude": (1740, 200),
       "Verdicts": (1900, 200), "Precision": (2080, 0), "Review the search": (0, 420), "Export?": (220, 420),
       "Stopped": (440, 600), "Export with Evaboot": (440, 400), "Wait 30 s": (660, 400), "Check the export": (880, 400),
       "Done?": (1100, 400), "Still running?": (1100, 560), "Lead rows": (1320, 400), "Add to your sheet": (1540, 400), "Every week?": (1760, 400),
       "Weekly?": (1980, 400), "Create the weekly export": (2200, 320), "Weekly export on": (2420, 320),
       "Leads saved": (2200, 500)}
for n in nodes:
    n["position"] = list(POS[n["name"]])

for a, b in [(FORM, "Your settings"), ("Your settings", "Build the search"), ("Build the search", "Wait 20 s"),
             ("Wait 20 s", "Check the build"), ("Check the build", "Built?"),
             ("Add size, industry and exclusions", "Preview 25 leads (free)"), ("Preview 25 leads (free)", "Judge the preview"),
             ("Judge the preview", "Precision"), ("Precision", "Review the search"), ("Review the search", "Export?"),
             ("Export with Evaboot", "Wait 30 s"), ("Wait 30 s", "Check the export"), ("Check the export", "Done?"),
             ("Lead rows", "Add to your sheet"), ("Add to your sheet", "Every week?"), ("Every week?", "Weekly?"),
             ("Create the weekly export", "Weekly export on")]:
    link(a, b)
link("Built?", "Add size, industry and exclusions", out=0)
link("Built?", "Wait 20 s", out=1)
link("Export?", "Export with Evaboot", out=0)
link("Export?", "Stopped", out=1)
link("Done?", "Lead rows", out=0)
link("Done?", "Still running?", out=1)
link("Still running?", "Wait 30 s")
link("Weekly?", "Create the weekly export", out=0)
link("Weekly?", "Leads saved", out=1)
link("Claude", "Judge the preview", "ai_languageModel")
link("Verdicts", "Judge the preview", "ai_outputParser")

workflow = {"name": "AI lead finder (Evaboot MCP + Claude)", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {}}
out = Path(__file__).with_name("ai-lead-finder.json")
out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
print(out, len(nodes), "nodes")
