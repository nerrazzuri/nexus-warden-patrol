#!/usr/bin/env python3
"""把设计的单一来源(``design/mobile.json``、``design/i18n/alerts.json``、``design/tokens.json``)
生成手机 App 用的 Dart 常量。2026-10-14 重做之后手机的设计系统是 ``mobile.json`` →
``nw_tokens.g.dart``;``tokens.json`` 归网页值班台,手机只从里面取动效(``tokens.g.dart`` 的
``D1Motion``)。

App 不在运行时读 JSON:颜色、字号是编译期常量,告警标题按种类查表。改了 ``design/`` 之后跑一遍::

    python3 tools/gen_mobile_design.py

``tests/test_design_mobile.py`` 会重新生成一遍跟仓库里的比,对不上就红(忘了跑的会被抓住)。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mobile" / "lib" / "design"

HEADER = "// 生成的文件,别手改:改 design/ 下的 JSON,再跑 python3 tools/gen_mobile_design.py。\n"


def _hex(c: str) -> str:
    m = re.fullmatch(r"#([0-9A-Fa-f]{6})", c)
    if m is None:
        raise ValueError(f"颜色要写成 #RRGGBB:{c!r}")
    return f"Color(0xFF{m.group(1).upper()})"


def _dart_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("$", "\\$") + "'"


def tokens_dart(tokens: dict) -> str:
    """``design/tokens.json`` 是网页值班台的令牌;手机 App 2026-10-14 换了设计系统(``mobile.json``),
    从这里只剩动效那三项还在用(告警页没确认的 P1 的闪法)。颜色、尺寸、圆角、字不再生成。"""
    motion = tokens["motion"]
    lines = [HEADER, f"const int tokensVersion = {int(tokens['version'])};\n",
             "/// 动效(``design/tokens.json`` 的 motion),毫秒。手机 App 从这份令牌里只用这三项。",
             "abstract final class D1Motion {",
             f"  static const int fast = {int(motion['fast'])};",
             f"  static const int p1FlashMs = {int(motion['p1FlashMs'])};",
             f"  static const double p1FlashMinOpacity = {float(motion['p1FlashMinOpacity'])};",
             "}"]
    return "\n".join(lines) + "\n"


def _hex_alpha(c: str) -> str:
    """``#RRGGBBAA``(压在视频上的那层带透明度)→ Dart 的 ``0xAARRGGBB``。"""
    m = re.fullmatch(r"#([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})", c)
    if m is None:
        raise ValueError(f"带透明度的颜色要写成 #RRGGBBAA:{c!r}")
    return f"Color(0x{m.group(2).upper()}{m.group(1).upper()})"


def nw_tokens_dart(mobile: dict) -> str:
    """新设计系统(``design/mobile.json``):浅色、深色两套颜色,间距,圆角,字体,字。"""
    light, dark = mobile["color"]["light"], mobile["color"]["dark"]
    if list(light) != list(dark):
        raise ValueError("浅色、深色两套颜色的键要一样、顺序也一样")
    lines = [HEADER, "import 'package:flutter/painting.dart' show Color, FontWeight, TextStyle;\n",
             f"const int nwTokensVersion = {int(mobile['version'])};\n"]
    for cls, doc, colors in (("NwLight", "浅色", light), ("NwDark", "深色", dark)):
        lines += [f"/// {doc}那一套颜色(``design/mobile.json`` 的 color)。",
                  f"abstract final class {cls} {{"]
        for name, value in colors.items():
            dart = _hex_alpha(value) if name == "scrim" else _hex(value)
            lines.append(f"  static const Color {name} = {dart};")
        lines.append("}\n")
    lines += ["/// 间距(space),逻辑像素。", "abstract final class NwSpace {"]
    for name, value in mobile["space"].items():
        lines.append(f"  static const double {name} = {float(value)};")
    lines += ["}\n", "/// 圆角(radius)。", "abstract final class NwRadius {"]
    for name, value in mobile["radius"].items():
        lines.append(f"  static const double {name} = {float(value)};")
    font = mobile["font"]
    fallback = ", ".join(_dart_str(f) for f in font["fallback"])
    lines += ["}\n", "/// 字体(font):标题、正文、等宽;中文落到系统字体。",
              "abstract final class NwFont {"]
    for name in ("display", "sans", "mono"):
        lines.append(f"  static const String {name} = {_dart_str(font[name])};")
    lines += [f"  static const List<String> fallback = <String>[{fallback}];", "}\n",
              "/// 字(type):不带颜色。", "abstract final class NwType {"]
    for name, t in mobile["type"].items():
        if t["family"] not in ("display", "sans", "mono"):
            raise ValueError(f"字体只有 display / sans / mono:{name}")
        if float(t["size"]) < 12:
            raise ValueError(f"字号最小 12:{name}")
        lines += [f"  static const TextStyle {name} = TextStyle(",
                  f"      fontFamily: NwFont.{t['family']},",
                  "      fontFamilyFallback: NwFont.fallback,",
                  f"      fontSize: {float(t['size'])},",
                  f"      height: {float(t['height'])},",
                  f"      fontWeight: FontWeight.w{int(t['weight'])},",
                  "      letterSpacing: 0.0);"]
    lines += ["}\n", "/// 哪种状态用哪种色调(usage);红只给 P1 和急停类,橙只给 P2 和低电。",
              "const Map<String, String> nwUsage = <String, String>{"]
    for use, tone in mobile["usage"].items():
        if use.startswith("$"):
            continue
        lines.append(f"  {_dart_str(use)}: {_dart_str(tone)},")
    lines.append("};")
    return "\n".join(lines) + "\n"


def alerts_dart(catalog: dict) -> str:
    lines = [HEADER,
             "/// 告警标题按种类(kind):``(英文, 中文)``。来源 ``design/i18n/alerts.json``。",
             "const Map<String, (String, String)> alertTitles = <String, (String, String)>{"]
    for kind, entry in catalog.items():
        if kind.startswith("$"):
            continue
        lines.append(f"  {_dart_str(kind)}: ({_dart_str(entry['en'])}, {_dart_str(entry['zh'])}),")
    lines.append("};")
    return "\n".join(lines) + "\n"


def nav_codes_dart() -> str:
    """导航 V1 第 5 节的失败原因码(单一来源 ``nexwar_contract.navcodes``)
    → 手机按码写说明和处理建议。"""
    src = ROOT / "packages" / "contract" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from nexwar_contract.navcodes import FAIL_CODES
    lines = [HEADER,
             "/// 导航失败原因码:``(英文, 中文, 英文处理建议, 中文处理建议)``。",
             "/// 来源 ``nexwar_contract.navcodes``。",
             "const Map<String, (String, String, String, String)> navFailCodes ="
             " <String, (String, String, String, String)>{"]
    for code, c in FAIL_CODES.items():
        lines.append(f"  {_dart_str(code)}: ({_dart_str(c.en)}, {_dart_str(c.zh)},")
        lines.append(f"      {_dart_str(c.action_en)}, {_dart_str(c.action_zh)}),")
    lines.append("};")
    return "\n".join(lines) + "\n"


def nav_codes_ts() -> str:
    """同一份码表给网页(报警详情按码写说明和处理建议)。"""
    src = ROOT / "packages" / "contract" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from nexwar_contract.navcodes import FAIL_CODES
    lines = ["// 生成的文件,别手改:改 nexwar_contract.navcodes,"
             "再跑 python3 tools/gen_mobile_design.py。",
             "",
             "/** 导航失败原因码:[英文, 中文, 英文处理建议, 中文处理建议]。 */",
             "export const NAV_FAIL_CODES: Record<string, "
             "readonly [string, string, string, string]> = {"]
    for code, c in FAIL_CODES.items():
        four = (c.en, c.zh, c.action_en, c.action_zh)
        vals = ", ".join(json.dumps(v, ensure_ascii=False) for v in four)
        lines.append(f"  {json.dumps(code)}: [{vals}],")
    lines.append("};")
    return "\n".join(lines) + "\n"


def _errcodes():
    src = ROOT / "packages" / "contract" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from nexwar_contract import errcodes
    return errcodes


def err_codes_ts() -> str:
    """错误码总表(日志设计 第 7 条)给网页:按十六进制码或英文名查说明、处理建议。"""
    ec = _errcodes()
    lines = ["// 生成的文件,别手改:改 nexwar_contract.errcodes,"
             "再跑 python3 tools/gen_mobile_design.py。",
             "",
             "/** 错误码:英文名 → [十六进制, 级别, 谁处理, 英文, 中文, 英文处理建议, 中文处理建议]。 */",
             "export const ERR_CODES: Record<string, readonly [string, string, string, string, "
             "string, string, string]> = {"]
    for c in ec.CODES.values():
        vals = ", ".join(json.dumps(v, ensure_ascii=False)
                         for v in (c.hex, c.level, c.who, c.en, c.zh, c.do_en, c.do_zh))
        lines.append(f"  {json.dumps(c.name)}: [{vals}],")
    lines.append("};")
    lines.append("/** 告警种类 → 错误码英文名。 */")
    lines.append("export const ALERT_ERR: Record<string, string> = {")
    for k, v in ec.ALERT.items():
        lines.append(f"  {json.dumps(k)}: {json.dumps(v)},")
    lines.append("};")
    return "\n".join(lines) + "\n"


def err_codes_dart() -> str:
    """同一份码表给手机。"""
    ec = _errcodes()
    lines = [HEADER,
             "/// 错误码:英文名 → ``(十六进制, 级别, 谁处理, 英文, 中文, 英文处理建议, 中文处理建议)``。",
             "/// 来源 ``nexwar_contract.errcodes``。",
             "const Map<String, (String, String, String, String, String, String, String)> errCodes ="
             " <String, (String, String, String, String, String, String, String)>{"]
    for c in ec.CODES.values():
        lines.append(f"  {_dart_str(c.name)}: ({_dart_str(c.hex)}, {_dart_str(c.level)}, "
                     f"{_dart_str(c.who)},")
        lines.append(f"      {_dart_str(c.en)}, {_dart_str(c.zh)},")
        lines.append(f"      {_dart_str(c.do_en)}, {_dart_str(c.do_zh)}),")
    lines.append("};")
    lines.append("")
    lines.append("/// 告警种类 → 错误码英文名。")
    lines.append("const Map<String, String> alertErr = <String, String>{")
    for k, v in ec.ALERT.items():
        lines.append(f"  {_dart_str(k)}: {_dart_str(v)},")
    lines.append("};")
    return "\n".join(lines) + "\n"


def err_manual_md() -> str:
    """《错误码手册》(给工程师、售后):按模块列每个码。"""
    ec = _errcodes()
    lv = {"info": "提示", "warn": "警告", "error": "严重"}
    who = {"user": "用户自己", "engineer": "工程师"}
    out = ["# 错误码手册", "",
           "> 生成的文件,别手改:改 `packages/contract/src/nexwar_contract/errcodes.py`,"
           "再跑 `python3 tools/gen_mobile_design.py`。", "",
           "错误码是十六进制 `0xMMRR`:高两位是模块,低两位是这个模块里的第几种原因。"
           "界面上显示十六进制码;日志里写成 `code=0x0201 dispatch.offline`,"
           "按十六进制码或英文名都能搜到。码定下来不改、不重复用。", "",
           "查问题的顺序:", "",
           "1. 在网页活动日志或告警里找到错误码和时间。",
           "2. 在诊断包的 `logs/site.log` 里搜这个码,看前后几行;"
           "方括号里的 `req=`、`task=` 编号能把同一件事的各条记录串起来。",
           "3. 涉及机器人的,用同一个 `task=` 编号在 `robot-logs/<机器人>/` 里搜。", ""]
    for m, (prefix, zh, _en) in ec.MODULES.items():
        rows = [c for c in ec.CODES.values() if c.module == m]
        if not rows:
            continue
        out += [f"## 0x{m:02X}xx {zh}(`{prefix}.*`)", "",
                "| 码 | 英文名 | 级别 | 谁处理 | 怎么回事 | 该做什么 |",
                "|---|---|---|---|---|---|"]
        for c in rows:
            out.append(f"| `{c.hex}` | `{c.name}` | {lv[c.level]} | {who[c.who]} | {c.zh} | "
                       f"{c.do_zh or '—'} |")
        out.append("")
    return "\n".join(out)


def generate() -> dict[Path, str]:
    tokens = json.loads((ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "design" / "i18n" / "alerts.json").read_text(encoding="utf-8"))
    mobile = json.loads((ROOT / "design" / "mobile.json").read_text(encoding="utf-8"))
    return {OUT / "tokens.g.dart": tokens_dart(tokens),
            OUT / "nw_tokens.g.dart": nw_tokens_dart(mobile),
            OUT / "alert_titles.g.dart": alerts_dart(catalog),
            OUT / "nav_codes.g.dart": nav_codes_dart(),
            ROOT / "web" / "console" / "src" / "navcodes.g.ts": nav_codes_ts(),
            OUT / "err_codes.g.dart": err_codes_dart(),
            ROOT / "web" / "console" / "src" / "errcodes.g.ts": err_codes_ts(),
            ROOT / "docs" / "错误码手册.md": err_manual_md()}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for path, text in generate().items():
        path.write_text(text, encoding="utf-8")
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
