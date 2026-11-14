#!/usr/bin/env python3
"""Read-only static indicator audit for the changed CounterFlame Mach-O files."""
import json, re, zipfile, hashlib
from pathlib import Path

STOCK="stock.ipa"
REFERENCE="reference.ipa"
MAIN="Payload/CounterFlame.app/CounterFlame"
DYLIB="Payload/CounterFlame.app/Frameworks/CounterFlameKAlert551.dylib"
TOKENS=re.compile(
    rb"(?i)(https?://[^\x00\s]{4,}|[a-z0-9._%+-]+\.(?:com|net|org|io|cn)\b|"
    rb"hook|substrate|substitute|ellekit|fishhook|dobby|frida|"
    rb"inventory|skin|unlock|entitle|purchase|iap|receipt|"
    rb"telegram|discord|analytics|crash|ads|advert|tracking|"
    rb"keychain|deviceid|identifier|certificate|provision|"
    rb"socket|websocket|curl|http|https|"
    rb"UnitySendMessage|il2cpp|mono|load|dlopen|dlsym)"
)
def extract(z, path):
    try: return z.read(path)
    except KeyError: return None
def hits(data):
    if not data: return []
    out=[]
    for m in TOKENS.finditer(data):
        s=m.group(0).decode("utf-8","replace").strip()
        if s not in out: out.append(s)
    return out[:250]
def sha(b): return hashlib.sha256(b).hexdigest() if b is not None else None
with zipfile.ZipFile(STOCK) as a, zipfile.ZipFile(REFERENCE) as b:
    stock_main=extract(a,MAIN); ref_main=extract(b,MAIN); dylib=extract(b,DYLIB)
    report={
      "scope":"Static strings/metadata triage only; no code execution and no entitlement patching.",
      "main_executable":{
        "stock_present":stock_main is not None,"reference_present":ref_main is not None,
        "stock_sha256":sha(stock_main),"reference_sha256":sha(ref_main),
        "same_length":len(stock_main)==len(ref_main) if stock_main and ref_main else None,
        "changed_byte_count":sum(x!=y for x,y in zip(stock_main,ref_main)) if stock_main and ref_main else None,
        "reference_indicators":hits(ref_main),
        "stock_indicators":hits(stock_main)
      },
      "added_dylib":{
        "present":dylib is not None,"size":len(dylib) if dylib else None,
        "sha256":sha(dylib),"indicators":hits(dylib)
      },
      "interpretation":"String matches are leads, not proof of behavior. A dylib can be unrelated or malicious. Runtime behavior and the actual skin selection path are not established by this report."
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/reference_binary_static_audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Reference binary static audit","",
      "Read-only string triage; no execution or patching.","",
      "## Main executable","",
      f"- Stock SHA-256: {report['main_executable']['stock_sha256']}",
      f"- Reference SHA-256: {report['main_executable']['reference_sha256']}",
      f"- Changed byte count: {report['main_executable']['changed_byte_count']}","",
      "Reference string indicators:"]
    lines += ["- `"+x+"`" for x in report["main_executable"]["reference_indicators"]] or ["- No selected indicators"]
    lines += ["","## Added dylib","",f"- Present: {dylib is not None}",f"- Size: {len(dylib) if dylib else 0} bytes",
              f"- SHA-256: {sha(dylib)}","","Selected strings:"]
    lines += ["- `"+x+"`" for x in report["added_dylib"]["indicators"]] or ["- No selected indicators"]
    lines += ["","## Limits","","String matches are leads, not proof of behavior. This report does not identify or reproduce any entitlement bypass."]
    Path("reports/reference_binary_static_audit.md").write_text("\n".join(lines),encoding="utf-8")
    print("Static audit complete; see reports/reference_binary_static_audit.md")
