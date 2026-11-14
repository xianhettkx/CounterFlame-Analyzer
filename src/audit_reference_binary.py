#!/usr/bin/env python3
"""Read-only static indicator audit for the changed CounterFlame Mach-O files."""
import json, re, zipfile, hashlib
from pathlib import Path

STOCK="stock.ipa"
REFERENCE="reference.ipa"
MAIN="Payload/CounterFlame.app/CounterFlame"
DYLIB="Payload/CounterFlame.app/Frameworks/CounterFlameKAlert551.dylib"
KEYWORDS=("skin","unlock","inventory","purchase","iap","receipt","substrate","hook",
          "dobby","frida","ellekit","substitute","telegram","deviceid","identifier",
          "analytics","advert","tracking","verify","activate","handshake","config",
          "status","http","https","dlopen","dlsym","il2cpp","mono","keychain")
def extract(z, path):
    try: return z.read(path)
    except KeyError: return None
def strings(data):
    if not data: return []
    found=[]
    for raw in re.findall(rb"[ -~]{5,}",data):
        s=raw.decode("ascii","replace").strip()
        if any(k in s.lower() for k in KEYWORDS) and s not in found:
            found.append(s)
    return found[:500]
def sha(b): return hashlib.sha256(b).hexdigest() if b is not None else None
with zipfile.ZipFile(STOCK) as a, zipfile.ZipFile(REFERENCE) as b:
    stock_main=extract(a,MAIN); ref_main=extract(b,MAIN); dylib=extract(b,DYLIB)
    report={
      "scope":"Read-only printable-string triage; binaries are not executed or modified.",
      "main_executable":{
        "stock_sha256":sha(stock_main),"reference_sha256":sha(ref_main),
        "same_length":len(stock_main)==len(ref_main) if stock_main and ref_main else None,
        "changed_byte_count":sum(x!=y for x,y in zip(stock_main,ref_main)) if stock_main and ref_main else None,
        "reference_strings":strings(ref_main),"stock_strings":strings(stock_main)},
      "added_dylib":{"present":dylib is not None,"size":len(dylib) if dylib else None,
        "sha256":sha(dylib),"strings":strings(dylib)},
      "interpretation":"Strings reveal embedded references only; they do not prove calls, control flow, or the actual unlock mechanism."
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/reference_binary_static_audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    lines=["# Reference binary static audit","",
      "Read-only printable-string triage; no code execution or patching.","",
      "## Main executable","",
      f"- Stock SHA-256: {sha(stock_main)}",f"- Reference SHA-256: {sha(ref_main)}",
      f"- Changed byte count: {report['main_executable']['changed_byte_count']}","",
      "Reference strings:"]
    lines += ["- `"+x+"`" for x in report["main_executable"]["reference_strings"]] or ["- No selected strings"]
    lines += ["","## Added dylib","",f"- Present: {dylib is not None}",f"- Size: {len(dylib) if dylib else 0} bytes",
              f"- SHA-256: {sha(dylib)}","","Relevant printable strings:"]
    lines += ["- `"+x+"`" for x in report["added_dylib"]["strings"]] or ["- No selected strings"]
    lines += ["","## Limits","","Embedded strings are not proof of runtime behavior. This report does not reconstruct or reproduce entitlement bypass logic."]
    Path("reports/reference_binary_static_audit.md").write_text("\n".join(lines),encoding="utf-8")
    print("Static string audit complete.")
