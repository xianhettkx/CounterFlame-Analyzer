#!/usr/bin/env python3
"""Read-only discovery of candidate UI/localization strings in Unity IPA assets."""
from __future__ import annotations
import argparse, json, re, zipfile
from collections import Counter
from pathlib import Path

ASCII_RUN = re.compile(rb"[ -~]{3,160}")
LIKELY = re.compile(r"[\u4e00-\u9fff]")

def human_text(value):
    value=value.strip()
    if not 2 <= len(value) <= 160:
        return False
    if any(ord(ch)<32 and ch not in "\\t\\r\\n" for ch in value):
        return False
    if sum(ch.isprintable() for ch in value)/len(value) < 0.98:
        return False
    # Keep actual Chinese text or readable natural-language labels; reject
    # binary payloads that merely decode into occasional CJK characters.
    if LIKELY.search(value):
        return True
    words=re.findall(r"[A-Za-z]{2,}",value)
    return bool(words) and (len(words)>=2 or (len(value)<=32 and value.isalpha()))

def walk(value, path="$"):
    if isinstance(value, str):
        if human_text(value):
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
                    # Strict decoding is intentional: binary TextAssets such as
                    # PVS/mesh payloads must never be treated as localization.
                    try:
                        text=src.decode("utf-8-sig", "strict")
                    except UnicodeDecodeError:
                        continue
                elif isinstance(src, str):
                    text=src
                else:
                    continue
                for line_no,line in enumerate(text.splitlines(),1):
                    line=line.strip()
                    if human_text(line):
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
                            if human_text(value):
                                found.append({"asset":archive_path,"path_id":obj.path_id,"type":typ,
                                              "name":getattr(data,"m_Name",""),"field":f"raw+{match.start()}","text":value})
        except Exception:
            continue
    return found


UI_WORDS = {"play","settings","inventory","market","store","loadout","weapon","weapons","gloves","stickers","agents","case","open","close","back","cancel","confirm","search","filter","buy","sell","equip","unequip","inspect","loading","error","retry","continue","exit","resume","matchmaking","ranked","casual","competitive","deathmatch","team","profile","friends"}

def native_candidate(value):
    value = value.strip().strip("\\x00")
    if not 2 <= len(value) <= 180 or not value.isprintable():
        return False
    if any(ch in value for ch in ("_", "/", "\\\\", "://", "{", "}", "<", ">", "$", "=")):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", value)
    if len(words) >= 2 and " " in value:
        return True
    return len(words) == 1 and words[0].casefold() in UI_WORDS

def scan_native_binaries(zf):
    """Read candidate strings from IL2CPP metadata and app binaries; never modify them."""
    candidates = {}
    wanted = ("global-metadata.dat", "/unityframework", "/counterflame")
    for info in zf.infolist():
        name = info.filename.lower()
        if not any(token in name for token in wanted) or info.file_size > 120 * 1024 * 1024:
            continue
        try:
            raw = zf.read(info)
        except Exception:
            continue
        patterns = (("ascii", re.compile(rb"[\\x20-\\x7e]{3,180}")),
                    ("utf16le", re.compile(rb"(?:[\\x20-\\x7e]\\x00){3,180}")))
        for encoding, pattern in patterns:
            for match in pattern.finditer(raw):
                try:
                    value = match.group().decode("ascii" if encoding == "ascii" else "utf-16le").strip()
                except UnicodeDecodeError:
                    continue
                if native_candidate(value):
                    key = (value, info.filename, encoding)
                    candidates.setdefault(key, {"text":value,"source":info.filename,"encoding":encoding,"offset":match.start()})
    return sorted(candidates.values(), key=lambda x:(x["text"].casefold(),x["source"],x["offset"]))

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
    native = scan_native_binaries(zf)
    native_report = {"mode":"read_only_native_string_discovery",
                     "binary_files_scanned":sorted({x["source"] for x in native}),
                     "candidate_occurrences":len(native),"strings":native}
    (out/"native_ui_string_candidates.json").write_text(json.dumps(native_report,ensure_ascii=True,indent=2),encoding="utf-8")
    counts=Counter(r["type"] for r in rows)
    print(json.dumps({"assets_scanned":scanned,"candidate_occurrences":len(rows),
                      "unique_strings":len(by_text),"by_type":dict(counts),
                      "native_candidates":len(native),"errors":len(errors)},ensure_ascii=False))
    print(f"[OK] {out/'localization_string_inventory.json'}")
if __name__=="__main__": main()
