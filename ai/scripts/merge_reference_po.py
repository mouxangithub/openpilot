#!/usr/bin/env python3
"""Merge reference app_zh-CHS.po translations into project po files."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "openpilot"
TRANSLATIONS = ROOT / "selfdrive/ui/translations"
REFERENCE = Path(r"C:\Users\mouxan\Downloads\app_zh-CHS.po")

spec = importlib.util.spec_from_file_location("potools", TRANSLATIONS / "potools.py")
potools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(potools)


def load_entries(path: Path) -> dict[str, potools.POEntry]:
  _, entries = potools.parse_po(path)
  return {e.msgid: e for e in entries if e.msgid}


def write_entries(path: Path, lang: str, entries: list[potools.POEntry]) -> None:
  potools.write_po(path, potools._build_po_header(lang), entries)


# Style-aligned overrides for strings only in project po (not in reference)
EXTRA_CHS = {
  "Enable \"Always Offroad\" in Device panel, or turn vehicle off to toggle.":
    "请在设备面板启用“始终非行车”，或熄火后再切换。",
  'Enable "Always Offroad" in Device panel, or turn vehicle off to change.':
    "请在设备面板启用“始终非行车”，或熄火后再更改。",
  'Please enable "Always Offroad" mode or turn off the vehicle to adjust these toggles.':
    "请启用“始终非行车”模式或熄火后再调整这些开关。",
  "MADS Screen Activation": "MADS 屏幕激活",
  "3-Finger": "三指",
  "4-Finger": "四指",
  "5-Finger": "五指",
  "Use a multi-finger press on the infotainment screen to toggle MADS.":
    "在车机屏幕多指按压可切换 MADS。",
  "This allows the use of full MADS functionality when enabled.":
    "开启后可使用完整 MADS 功能。",
  "Selecting a higher finger count may reduce accidental activations.":
    "提高手指数量，可减少误触发。",
  "Note: Setting this to Off will reset your MADS settings to default.":
    "注意：设为关闭会重置 MADS 为默认设置。",
  "Adjust Camera Offset": "调整摄像头偏移",
  "Virtually shift camera's perspective to move model's center to Left(+ values) or Right (- values)":
    "虚拟调整摄像头视角，正值向左、负值向右移动模型中心。",
  "Frequently Asked Questions": "常见问题",
  "Does it matter how or where I drive?": "怎么开、在哪开重要吗？",
  "Nope, just drive as you normally would.": "不重要，正常开就行。",
  "Do all of my segments get pulled in Firehose Mode?": "Firehose 模式会上传全部片段吗？",
  "No, we selectively pull a subset of your segments.": "不会，只会抽取部分片段。",
  "What's a good USB-C adapter?": "USB-C 充电器怎么选？",
  "Any fast phone or laptop charger should be fine.": "手机或笔记本快充头都可以。",
  "Does it matter which software I run?": "用什么软件重要吗？",
  "Yes, only upstream openpilot (and particular forks) are able to be used for training.":
    "重要，只有上游 openpilot（及指定分支）可用于训练。",
  "Enable Accel Controller": "启用加减速控制",
  "Begin slowing early and smoothly behind lead vehicles. Stock longitudinal control retains braking and stopping authority.":
    "跟车时更早、更平顺地减速。原车纵向控制仍保留制动和停车权限。",
  "Acceleration Profile": "加速风格",
  "Eco slows earliest and recovers gently, Normal balances comfort and response, and Sport reacts and recovers more quickly.":
    "节能最早减速、恢复更柔和；标准兼顾舒适和响应；运动反应更快。",
  "Eco": "节能",
  "Normal": "标准",
  "Sport": "运动",
  "enable accel controller": "启用加减速控制",
  "acceleration profile": "加速风格",
  "eco": "节能",
  "normal": "标准",
  "sport": "运动",
  "Block Lane Change: Road Edge Detection": "阻止变道：路沿检测",
  "Blocks the lane change if the model sees a road edge on your signaled side.":
    "若模型在转向灯一侧检测到道路边缘，将阻止变道。",
  "aggressive": "激进",
  "standard": "标准",
  "relaxed": "从容",
  "distraction detection level": "分心检测灵敏度",
  "strict": "严格",
  "moderate": "适中",
  "lenient": "宽松",
  "firehose": "Firehose",
  "Distraction Detection Level": "分心检测灵敏度",
  "ETH": "ETH",
  "OSM": "OSM",
  "km/h": "km/h",
  "mph": "mph",
  "comma prime": "comma prime",
  "SCC-M": "SCC-M",
  "SCC-V": "SCC-V",
  "PANDA": "PANDA",
  "{} s": "{} s",
  "{} %": "{} %",
  "{} segment of your driving is in the training dataset so far.":
    "目前已有 {} 个您的驾驶片段被纳入训练数据集。",
}

PLURAL_CHS = {
  "{} segment of your driving is in the training dataset so far.": [
    "目前已有 {} 个您的驾驶片段被纳入训练数据集。",
    "目前已有 {} 个您的驾驶片段被纳入训练数据集。",
  ],
}
PLURAL_CHT = {
  "{} segment of your driving is in the training dataset so far.": [
    "目前已有 {} 個您的駕駛片段被納入訓練資料集。",
    "目前已有 {} 個您的駕駛片段被納入訓練資料集。",
  ],
}

EXTRA_CHT = {
  k: v.replace("设备", "裝置").replace("设置", "設定").replace("启用", "啟用")
      .replace("关闭", "關閉").replace("驾驶", "駕駛").replace("屏幕", "螢幕")
      .replace("摄像头", "攝影機").replace("减速", "減速").replace("制动", "制動")
      .replace("训练", "訓練").replace("软件", "軟體").replace("充电", "充電")
      .replace("片段", "片段").replace("检测", "偵測").replace("宽松", "寬鬆")
      .replace("适中", "適中").replace("从容", "從容").replace("灵敏度", "靈敏度")
  for k, v in EXTRA_CHS.items()
}
EXTRA_CHT.update({
  "Enable \"Always Offroad\" in Device panel, or turn vehicle off to toggle.":
    "請在裝置面板啟用「始終非行車」，或熄火後再切換。",
  'Enable "Always Offroad" in Device panel, or turn vehicle off to change.':
    "請在裝置面板啟用「始終非行車」，或熄火後再更改。",
  'Please enable "Always Offroad" mode or turn off the vehicle to adjust these toggles.':
    "請啟用「始終非行車」模式或熄火後再調整這些開關。",
  "MADS Screen Activation": "MADS 螢幕啟用",
  "Frequently Asked Questions": "常見問題",
  "Does it matter how or where I drive?": "怎麼開、在哪開重要嗎？",
  "Nope, just drive as you normally would.": "不重要，正常開就行。",
  "Do all of my segments get pulled in Firehose Mode?": "Firehose 模式會上傳全部片段嗎？",
  "No, we selectively pull a subset of your segments.": "不會，只會抽取部分片段。",
  "What's a good USB-C adapter?": "USB-C 充電器怎麼選？",
  "Any fast phone or laptop charger should be fine.": "手機或筆電快充頭都可以。",
  "Does it matter which software I run?": "用什麼軟體重要嗎？",
  "Yes, only upstream openpilot (and particular forks) are able to be used for training.":
    "重要，只有上游 openpilot（及指定分支）可用於訓練。",
  "Enable Accel Controller": "啟用加減速控制",
  "Acceleration Profile": "加速風格",
  "enable accel controller": "啟用加減速控制",
  "acceleration profile": "加速風格",
  "distraction detection level": "分心偵測靈敏度",
  "relaxed": "從容",
})


def merge_reference(target_path: Path, lang: str, extra: dict[str, str], plurals: dict[str, list[str]]) -> tuple[int, int]:
  ref = load_entries(REFERENCE)
  _, entries = potools.parse_po(target_path)
  ref_hits = extra_hits = 0
  for e in entries:
    if e.is_plural and e.msgid in ref and ref[e.msgid].msgstr_plural:
      if e.msgstr_plural != ref[e.msgid].msgstr_plural:
        e.msgstr_plural = dict(ref[e.msgid].msgstr_plural)
        ref_hits += 1
      continue
    if e.is_plural and e.msgid in plurals:
      new = {i: v for i, v in enumerate(plurals[e.msgid])}
      if e.msgstr_plural != new:
        e.msgstr_plural = new
        extra_hits += 1
      continue
    if e.msgid in ref and ref[e.msgid].msgstr:
      if e.msgstr != ref[e.msgid].msgstr:
        e.msgstr = ref[e.msgid].msgstr
        ref_hits += 1
      continue
    if e.msgid in extra and extra[e.msgid] and e.msgstr != extra[e.msgid]:
      e.msgstr = extra[e.msgid]
      extra_hits += 1
  write_entries(target_path, lang, entries)
  return ref_hits, extra_hits


def main():
  n1, e1 = merge_reference(TRANSLATIONS / "app_zh-CHS.po", "zh-CHS", EXTRA_CHS, PLURAL_CHS)
  n2, e2 = merge_reference(TRANSLATIONS / "app_zh-CHT.po", "zh-CHT", EXTRA_CHT, PLURAL_CHT)
  print(f"zh-CHS: {n1} from reference, {e1} style overrides")
  print(f"zh-CHT: {n2} from reference, {e2} style overrides")


if __name__ == "__main__":
  main()
