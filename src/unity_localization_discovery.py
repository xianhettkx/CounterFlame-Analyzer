#!/usr/bin/env python3
"""Read-only discovery of candidate UI/localization strings in Unity IPA assets."""
from __future__ import annotations
import argparse, json, re, zipfile
from collections import Counter
from pathlib import Path

ASCII_RUN = re.compile(rb"[ -~]{3,160}")
LIKELY = re.compile(r"[\u4e00-\u9fff]")

def walk(value, path="$"):
    if isinstance(value, str):
        if 2 <= len(value.strip()) <= 160 and LIKELY.search(value):
            yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            yield from walk(v, f"{path}[{i}]")

def scan_blob(raw, archive_path):
    import UnityPy
    env = UnityPy.load(raw)
    found=[]
    for obj in env.objects:
        typ=obj.type.name
        try:
            if typ == "TextAsset":
                data=obj.read()
                src=getattr(data,"m_Script",None)
                if isinstance(src, bytes):
                    text=src.decode("utf-8-sig", "ignore")
                elif isinstance(src, str):
                    text=src
                else:
                    continue
                for line_no,line in enumerate(text.splitlines(),1):
                    line=line.strip()
                    if 2 <= len(line) <= 160 and LIKELY.search(line):
                        found.append({"asset":archive_path,"path_id":obj.path_id,"type":typ,
                                      "name":getattr(data,"m_Name",""),"field":f"line:{line_no}","text":line})
            elif typ == "MonoBehaviour":
                try:
                    tree=obj.read_typetree()
                    for field,value in walk(tree):
                        found.append({"asset":archive_path,"path_id":obj.path_id,"type":typ,
                                      "name":str(tree.get("m_Name","")),"field":field,"text":value})
                except Exception:
                    # Preserve evidence only; do not attempt to infer or patch unknown binary layouts.
                    data=obj.read()
                    raw_data=getattr(data,"raw_data",b"")
                    if isinstance(raw_data,bytes):
                        for match in ASCII_RUN.finditer(raw_data):
                            value=match.group().decode("ascii","ignore").strip()
                            if LIKELY.search(value):
                                found.append({"asset":archive_path,"path_id":obj.path_id,"type":typ,
                                              "name":getattr(data,"m_Name",""),"field":f"raw+{match.start()}","text":value})
        except Exception:
            continue
    return found

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("ipa")
    ap.add_argument("--out",default="reports/localization_discovery")
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    rows=[]; scanned=0; errors=[]
    with zipfile.ZipFile(args.ipa) as zf:
        targets=[i for i in zf.infolist() if i.filename.lower().endswith((".bundle",".assets"))]
        for info in targets:
            scanned+=1
            try: rows.extend(scan_blob(zf.read(info),info.filename))
            except Exception as e: errors.append({"asset":info.filename,"error":f"{type(e).__name__}: {e}"[:240]})
    # Deduplicate exact string values while retaining all observed locations.
    by_text={}
    for row in rows:
        key=row["text"]
        by_text.setdefault(key,{"text":key,"occurrences":[]})["occurrences"].append(
            {k:row[k] for k in ("asset","path_id","type","name","field")})
    report={"mode":"read_only_string_discovery","assets_scanned":scanned,
            "candidate_occurrences":len(rows),"unique_strings":len(by_text),
            "errors":errors,"strings":sorted(by_text.values(),key=lambda x:(x["text"].casefold(),x["text"]))}
    (out/"localization_string_inventory.json").write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding="utf-8")
    counts=Counter(r["type"] for r in rows)
    print(json.dumps({"assets_scanned":scanned,"candidate_occurrences":len(rows),
                      "unique_strings":len(by_text),"by_type":dict(counts),"errors":len(errors)},ensure_ascii=False))
    print(f"[OK] {out/'localization_string_inventory.json'}")
if __name__=="__main__": main()
