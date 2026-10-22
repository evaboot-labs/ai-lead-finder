"""Helpers for the AI lead finder. The agent builds and tightens the Sales Navigator search through the
Evaboot MCP and judges each preview; these commands keep the score, the report and the weekly
de-duplication the same on every run. Nothing here touches the network.

    python3 finder.py rounds data/rounds.json                 precision per round: tighten or export
    python3 finder.py report data/export.json                 what the export holds, and its email rate
    python3 finder.py csv data/export.json [--seen data/seen.txt] > data/leads.csv   clean CSV, new people only
"""
import argparse
import collections
import csv
import json
import re
import sys

TARGET = 0.8   # share of the preview that must fit before you spend credits; TARGET.md can change it
MIN_JUDGED = 20
COLUMNS = ["First Name", "Last Name", "Current Job", "Company Name", "Company Domain", "Email", "Email Status",
           "Company Employee Range", "Company Industry", "Location", "Linkedin URL Public"]


def target():
    try:
        m = re.search(r"Precision target: (\d+)%", open("TARGET.md").read())
        return int(m.group(1)) / 100 if m else TARGET
    except FileNotFoundError:
        return TARGET


def rounds(path):
    """rounds.json: [{round, change, url, total, sample: [{title, company, fit, reason}]}], one per preview."""
    data = json.load(open(path))
    goal = target()
    problems = []
    print(f"{'round':<6}{'results':>9}{'fit':>9}  change")
    for r in data:
        sample = r.get("sample") or []
        if len(sample) < MIN_JUDGED:
            problems.append(f"round {r.get('round')}: judge at least {MIN_JUDGED} previewed leads, not {len(sample)}")
        if any(s.get("fit") not in (True, False) for s in sample):
            problems.append(f"round {r.get('round')}: every previewed lead needs fit true or false")
        if any(not s.get("fit") and not str(s.get("reason") or "").strip() for s in sample):
            problems.append(f"round {r.get('round')}: every lead that does not fit needs a reason")
        fit = sum(1 for s in sample if s.get("fit"))
        share = fit / len(sample) if sample else 0
        print(f"{r.get('round', '?'):<6}{r.get('total') or 0:>9,}{fit:>4}/{len(sample):<4}  {r.get('change', '')}")
    if not data:
        sys.exit("no round yet: preview the search and judge it first")
    last = data[-1].get("sample") or []
    misses = collections.Counter(s.get("reason", "") for s in last if not s.get("fit"))
    for reason, n in misses.most_common():
        print(f"  still in the last preview: {n} x {reason}")
    for p in problems:
        print("FAIL", p)
    share = sum(1 for s in last if s.get("fit")) / len(last) if last else 0
    verdict = "ready to export" if share >= goal and not problems else f"tighten: {share:.0%} fit, the target is {goal:.0%}"
    print(f"verdict: {verdict}")
    return 1 if problems or share < goal else 0


def prospects(path):
    return json.load(open(path)).get("prospects") or []


def report(path):
    """How many leads, how many usable emails, and where they work. Read it before you load anything."""
    leads = prospects(path)
    if not leads:
        sys.exit("the export holds no lead")
    status = collections.Counter((p.get("Email Status") or "not found").lower() for p in leads)
    sizes = collections.Counter(p.get("Company Employee Range") or "unknown" for p in leads)
    industries = collections.Counter(p.get("Company Industry") or "unknown" for p in leads)
    companies = collections.Counter(p.get("Company Name") for p in leads)
    n = len(leads)
    print(f"{n} leads, {sum(1 for p in leads if p.get('Email'))} with an email")
    for s, c in status.most_common():
        print(f"  email {s}: {c} ({c / n:.0%})")
    print("company size: " + ", ".join(f"{k} {v}" for k, v in sizes.most_common()))
    print("industry: " + ", ".join(f"{k} {v}" for k, v in industries.most_common(5)))
    twice = [c for c, k in companies.items() if c and k > 1]
    if twice:
        print("more than one lead at: " + ", ".join(twice))
    return 0


def to_csv(path, seen_path):
    """One clean row per lead. With --seen, only people not exported before, and the file is updated."""
    seen = set()
    if seen_path:
        try:
            seen = {line.strip() for line in open(seen_path) if line.strip()}
        except FileNotFoundError:
            pass
    w = csv.writer(sys.stdout)
    w.writerow(COLUMNS)
    new = []
    for p in prospects(path):
        key = p.get("Linkedin URL Unique ID") or p.get("Linkedin URL Public") or p.get("Full Name")
        if not key or key in seen:
            continue
        seen.add(key)
        new.append(key)
        w.writerow([p.get(c) or "" for c in COLUMNS])
    if seen_path:
        with open(seen_path, "a") as f:
            f.writelines(k + "\n" for k in new)
    print(f"{len(new)} new leads", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rounds").add_argument("rounds")
    sub.add_parser("report").add_argument("export")
    a = sub.add_parser("csv"); a.add_argument("export"); a.add_argument("--seen")
    args = ap.parse_args()
    if args.cmd == "rounds":
        sys.exit(rounds(args.rounds))
    if args.cmd == "report":
        sys.exit(report(args.export))
    sys.exit(to_csv(args.export, args.seen))


if __name__ == "__main__":
    main()
