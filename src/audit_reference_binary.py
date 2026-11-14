#!/usr/bin/env python3
"""Read-only static string triage for the reference IPA's added iOS dylib."""
import json, re, zipfile, hashlib, subprocess
from pathlib import Path

STOCK="stock.ipa"
REFERENCE="reference.ipa"
MAIN="Payload/CounterFlame.app/CounterFlame"
DYLIB="Payload/CounterFlame.app/Frameworks/CounterFlameKAlert551.dylib"
UI_TERMS=("menu","overlay","window","button","skin","glove","knife","inventory","unlock",
          "weapon","model","texture","paint","finish","sticker","agent","display","visual",
          "config","setting","enable","disable","close","open","language","chinese","english",
          "vip","free","aim","esp","wall","speed","jump","recoil","ads","advert","telegram",
          "verify","activate","deviceid","handshake","purchase","receipt","hook","substrate",
          "il2cpp","dlopen","dlsym","analytics","tracking")
def sha(b): return hashlib.sha256(b).hexdigest() if b is not None else None
def printable(data, minlen=4):
    return [x.decode("utf-8","replace").strip() for x in re.findall(rb"[ -~]{"+str(minlen).encode()+rb",}",data or b"")]
def extract(z,p):
    try:return z.read(p)
    except KeyError:return None
with zipfile.ZipFile(STOCK) as a, zipfile.ZipFile(REFERENCE) as b:
    sm=extract(a,MAIN); rm=extract(b,MAIN); dylib=extract(b,DYLIB)
    all_ascii=printable(dylib)
    selected=[]
    for s in all_ascii:
        low=s.lower()
        if any(t in low for t in UI_TERMS) and s not in selected:
            selected.append(s)
    # Include nearby strings in original order, so labels and endpoint names retain context.
    indexed=[]
    for i,s in enumerate(all_ascii):
        if s in selected:
            indexed.append({"index":i,"text":s,
              "before":all_ascii[max(0,i-2):i],"after":all_ascii[i+1:i+3]})
    report={
      "scope":"Read-only printable-string extraction; no code execution, patching, or entitlement modification.",
      "main_executable":{"stock_sha256":sha(sm),"reference_sha256":sha(rm),
        "same_length":len(sm)==len(rm) if sm and rm else None,
        "changed_byte_count":sum(x!=y for x,y in zip(sm,rm)) if sm and rm else None,
        "reference_selected_strings":printable(rm)},
      "added_dylib":{"present":dylib is not None,"size":len(dylib) if dylib else None,
        "sha256":sha(dylib),"ascii_string_count":len(all_ascii),
        "selected_strings_with_context":indexed[:1200]},
      "interpretation":"Strings identify embedded labels/references only. They do not prove which menu buttons exist or what runtime actions they perform."
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/reference_binary_static_audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Reference dylib UI/string triage","",
      "Read-only static string extraction. No code execution or patching.","",
      "## Main executable","",
      f"- Stock SHA-256: {sha(sm)}",f"- Reference SHA-256: {sha(rm)}",
      f"- Changed byte count: {report['main_executable']['changed_byte_count']}","",
      "## Added dylib","",
      f"- Present: {dylib is not None}",f"- Size: {len(dylib) if dylib else 0} bytes",
      f"- Printable ASCII strings: {len(all_ascii)}","",
      "## UI / skin / configuration / network-related strings",""]
    for item in indexed[:1200]:
        lines.append(f"- [{item['index']}] `{item['text']}`")
        if item["before"]: lines.append("  - before: "+ " | ".join(item["before"]))
        if item["after"]: lines.append("  - after: "+ " | ".join(item["after"]))
    lines += ["","## Limits","","These are embedded strings, not verified UI labels or runtime actions. Network endpoints and device identifiers warrant caution. No entitlement bypass logic is reconstructed."]
    Path("reports/reference_binary_static_audit.md").write_text("\n".join(lines),encoding="utf-8")
    print(f"Static triage complete: {len(all_ascii)} printable strings; {len(indexed)} selected.")
