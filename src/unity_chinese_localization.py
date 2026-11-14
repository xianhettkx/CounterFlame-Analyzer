#!/usr/bin/env python3
"""Apply conservative Simplified-Chinese UI string replacements to Unity text fields.

Only exact, reviewed UI labels are translated. Unknown strings are preserved.
The tool does not alter network, inventory, matchmaking, anti-cheat, or gameplay logic.
"""
from __future__ import annotations
import argparse, io, json, re, zipfile
from pathlib import Path
from typing import Any

# Exact labels and phrases commonly exposed by the game's menus and HUD.
ZH = {
    "Play": "开始游戏", "Play Now": "立即开始", "Quick Play": "快速开始",
    "Home": "首页", "Main Menu": "主菜单", "Inventory": "库存",
    "Loadout": "装备", "Store": "商店", "Market": "市场",
    "Settings": "设置", "Options": "选项", "Profile": "个人资料",
    "Friends": "好友", "Missions": "任务", "Mission": "任务",
    "Battle Pass": "通行证", "Rewards": "奖励", "Reward": "奖励",
    "News": "公告", "Events": "活动", "Clans": "战队",
    "Match": "对局", "Matchmaking": "匹配中", "Find Match": "开始匹配",
    "Searching": "正在搜索", "Search": "搜索", "Cancel": "取消",
    "Confirm": "确认", "Back": "返回", "Exit": "退出",
    "Resume": "继续游戏", "Restart": "重新开始", "Quit": "离开",
    "Continue": "继续", "Start": "开始", "Ready": "准备就绪",
    "Not Ready": "未准备", "Invite": "邀请", "Accept": "接受",
    "Decline": "拒绝", "Equip": "装备", "Equipped": "已装备",
    "Unequip": "卸下", "Inspect": "检视", "Buy": "购买",
    "Purchase": "购买", "Sell": "出售", "Upgrade": "升级",
    "Open": "打开", "Close": "关闭", "Apply": "应用",
    "Save": "保存", "Delete": "删除", "Remove": "移除",
    "Language": "语言", "Audio": "音频", "Sound": "声音",
    "Graphics": "画面", "Controls": "操作设置", "Sensitivity": "灵敏度",
    "Crosshair": "准星", "Gameplay": "游戏设置", "Video": "视频",
    "Music Volume": "音乐音量", "SFX Volume": "音效音量",
    "Master Volume": "主音量", "Voice Chat": "语音聊天",
    "On": "开启", "Off": "关闭", "Enabled": "已启用",
    "Disabled": "已禁用", "Low": "低", "Medium": "中",
    "High": "高", "Ultra": "极高", "Auto": "自动",
    "Login": "登录", "Log In": "登录", "Sign In": "登录",
    "Log Out": "退出登录", "Username": "用户名", "Password": "密码",
    "Loading": "加载中", "Connecting": "正在连接",
    "Reconnecting": "正在重新连接", "Waiting": "等待中",
    "Error": "错误", "Success": "成功", "Failed": "失败",
    "Retry": "重试", "Network Error": "网络错误",
    "Victory": "胜利", "Defeat": "失败", "Draw": "平局",
    "Score": "得分", "Kills": "击杀", "Deaths": "死亡",
    "Assists": "助攻", "Round": "回合", "Rounds": "回合",
    "Team": "队伍", "Spectator": "观战者",
    "Terrorists": "恐怖分子", "Counter-Terrorists": "反恐精英",
    "Bomb": "炸弹", "Plant": "安放炸弹", "Defuse": "拆除炸弹",
    "Time": "时间", "Health": "生命值", "Armor": "护甲",
    "Ammo": "弹药", "Reload": "换弹", "Buy Menu": "购买菜单",
    "Round Start": "回合开始", "Round Over": "回合结束",
    "You Win": "你赢了", "You Lose": "你输了",
    "Tap to Continue": "点击继续", "Press to Continue": "按下继续",
    "No Items": "暂无物品", "Coming Soon": "即将推出",
    "Are you sure?": "确定吗？", "Are you sure you want to quit?": "确定要退出吗？",
}

def translate_value(value: Any, stats: dict, context: str = "", allow_all: bool = False) -> Any:
    if isinstance(value, str):
        text_field = any(token in context.lower() for token in ("text", "label", "title", "desc", "message", "content", "placeholder", "tooltip", "caption", "button", "localiz"))
        translated = ZH.get(value.strip()) if (allow_all or text_field) else None
        if translated is not None and value == value.strip():
            stats[value] = stats.get(value, 0) + 1
            return translated
        return value
    if isinstance(value, list):
        return [translate_value(v, stats, context, allow_all) for v in value]
    if isinstance(value, dict):
        # Preserve keys: localization keys can be identifiers used by game code.
        return {k: translate_value(v, stats, str(k), allow_all) for k, v in value.items()}
    return value

def process_entry(raw: bytes, label: str):
    import UnityPy
    env = UnityPy.load(raw)
    changed = False
    stats = {}
    for obj in env.objects:
        try:
            if obj.type.name == "TextAsset":
                data = obj.read()
                src = getattr(data, "m_Script", None)
                if isinstance(src, bytes):
                    try: text = src.decode("utf-8-sig")
                    except UnicodeDecodeError: continue
                    # Parse structured localization tables and translate values only.
                    try:
                        parsed = json.loads(text)
                        new_obj = translate_value(parsed, stats, allow_all=True)
                        if new_obj != parsed:
                            data.m_Script = json.dumps(new_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                            obj.save()
                            changed = True
                    except (ValueError, TypeError):
                        # For plain text files, replace only complete lines, never substrings.
                        lines = text.splitlines(keepends=True)
                        new_lines = []
                        for line in lines:
                            body = line.rstrip("\r\n")
                            ending = line[len(body):]
                            new = ZH.get(body)
                            if new is not None:
                                stats[body] = stats.get(body, 0) + 1
                                new_lines.append(new + ending)
                            else:
                                new_lines.append(line)
                        new_text = "".join(new_lines)
                        if new_text != text:
                            data.m_Script = new_text.encode("utf-8")
                            obj.save()
                            changed = True
            elif obj.type.name == "MonoBehaviour":
                try:
                    tree = obj.read_typetree()
                except Exception:
                    continue
                new_tree = translate_value(tree, stats, allow_all=False)
                if new_tree != tree:
                    obj.save_typetree(new_tree)
                    changed = True
        except Exception:
            # A single unsupported Unity object must not abort the whole IPA scan.
            continue
    if not changed:
        return None, stats
    try:
        saved = env.file.save()
        if isinstance(saved, tuple):
            saved = saved[0]
        return bytes(saved), stats
    except Exception as exc:
        raise RuntimeError(f"failed to serialize {label}: {type(exc).__name__}: {exc}") from exc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ipa")
    ap.add_argument("--out-dir", default="reports/chinese_localization")
    args = ap.parse_args()
    out = Path(args.out_dir)
    files = out / "files"
    files.mkdir(parents=True, exist_ok=True)
    report = {"language": "简体中文", "mode": "exact-reviewed-labels", "entries_scanned": 0,
              "entries_patched": 0, "translated_occurrences": 0, "translations": {},
              "patched_entries": [], "errors": [], "limitations": [
                  "仅替换已审核且完全匹配的界面文本；未识别的文本保持原样。",
                  "若游戏把文字烘焙在图片中，或使用加密/外置语言包，本补丁不会修改它们。",
                  "中文字体字形是否完整取决于游戏原有字体资源；本流程不替换字体。"
              ]}
    with zipfile.ZipFile(args.ipa, "r") as zf:
        for info in zf.infolist():
            low = info.filename.lower()
            if not (low.endswith(".bundle") or low.endswith(".assets")):
                continue
            report["entries_scanned"] += 1
            try:
                patched, counts = process_entry(zf.read(info), info.filename)
                for k, n in counts.items():
                    report["translations"][k] = report["translations"].get(k, 0) + n
                    report["translated_occurrences"] += n
                if patched is not None:
                    target = files / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(patched)
                    report["entries_patched"] += 1
                    report["patched_entries"].append({"path": info.filename, "bytes": len(patched),
                                                      "translated_occurrences": sum(counts.values())})
            except Exception as exc:
                report["errors"].append({"path": info.filename, "error": f"{type(exc).__name__}: {exc}"[:300]})
    report["translation_count"] = len(report["translations"])
    (out / "chinese_localization_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("entries_scanned","entries_patched","translated_occurrences","translation_count","errors")}, ensure_ascii=False))
    print(f"[OK] Report: {out / 'chinese_localization_report.json'}")

if __name__ == "__main__":
    main()
