#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from lunar_python import Solar

TIMEZONE_NAME = "Asia/Shanghai"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)
# 主流万年历：早子 + 十一时辰 + 夜子（13 段）
HOUR_WINDOWS = [
    "00:00-00:59",
    "01:00-02:59",
    "03:00-04:59",
    "05:00-06:59",
    "07:00-08:59",
    "09:00-10:59",
    "11:00-12:59",
    "13:00-14:59",
    "15:00-16:59",
    "17:00-18:59",
    "19:00-20:59",
    "21:00-22:59",
    "23:00-23:59",
]
HOUR_RULE_NOTE = "时辰：早子 00:00-00:59，夜子 23:00-23:59 单列"
SOURCE_NOTE = "数据：lunar-python（6tail）离线民用黄历，无外部 API"
FONT_SANS = (
    "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',"
    "'Noto Sans CJK SC','Noto Sans SC',Arial,sans-serif"
)
FONT_SERIF = (
    "'Songti SC','STSong','SimSun',"
    "'Noto Serif CJK SC','Noto Serif SC',serif"
)


@dataclass
class TermInfo:
    name: str
    date: str


@dataclass
class CalendarResult:
    solar_date: str
    weekday: str
    lunar_date: str
    ganzhi: str
    current_term: TermInfo
    next_term: TermInfo
    today_term_exact: bool
    holidays: list[str]
    zodiac_clash: str
    officer12: str
    day_star: str
    day_path: str
    level_name: str
    level_short: str
    peng_taboo: str
    fetal_god: str
    directions: list[str]
    star28: str
    nayin: str
    good_gods: list[str]
    bad_gods: list[str]
    good_things: list[str]
    bad_things: list[str]
    hour_luck: list[dict[str, str]]


@dataclass
class RenderedReport:
    subject: str
    text: str
    markdown: str
    html: str


def normalize_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    raw = str(value).strip()
    if not raw or raw.lower() == "none":
        return []
    parts = [part.strip() for part in re.split(r"[、，,;；\s]+", raw) if part.strip()]
    return parts if parts else [raw]


def parse_target_datetime(raw: str | None) -> datetime:
    now = datetime.now(TIMEZONE)
    if not raw or raw.strip().lower() in {"now", "today", "今天"}:
        return now
    token = raw.strip().lower()
    if token in {"tomorrow", "明天"}:
        return now + timedelta(days=1)
    if token in {"yesterday", "昨天"}:
        return now - timedelta(days=1)

    original = raw.strip()
    for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
        try:
            parsed = datetime.strptime(original, fmt)
            if fmt == "%Y-%m-%d":
                parsed = parsed.replace(hour=12, minute=0, second=0)
            return parsed.replace(tzinfo=TIMEZONE)
        except ValueError:
            continue
    raise SystemExit("无法识别日期格式，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")


def build_solar(dt: datetime) -> Solar:
    local = dt.astimezone(TIMEZONE) if dt.tzinfo else dt.replace(tzinfo=TIMEZONE)
    return Solar.fromYmdHms(
        local.year, local.month, local.day, local.hour, local.minute, local.second
    )


def get_current_term(lunar_obj: Any, dt: datetime) -> TermInfo:
    current = lunar_obj.getCurrentJieQi()
    if current is not None:
        solar = current.getSolar()
        return TermInfo(
            name=str(current.getName()),
            date=f"{solar.getYear():04d}-{solar.getMonth():02d}-{solar.getDay():02d}",
        )
    prev = lunar_obj.getPrevJieQi(True)
    solar = prev.getSolar()
    return TermInfo(
        name=str(prev.getName()),
        date=f"{solar.getYear():04d}-{solar.getMonth():02d}-{solar.getDay():02d}",
    )


def get_next_term(lunar_obj: Any) -> TermInfo:
    nxt = lunar_obj.getNextJieQi(True)
    solar = nxt.getSolar()
    return TermInfo(
        name=str(nxt.getName()),
        date=f"{solar.getYear():04d}-{solar.getMonth():02d}-{solar.getDay():02d}",
    )


def get_holidays(solar_obj: Any, lunar_obj: Any) -> list[str]:
    values = [
        solar_obj.getFestivals(),
        solar_obj.getOtherFestivals(),
        lunar_obj.getFestivals(),
        lunar_obj.getOtherFestivals(),
    ]
    merged: list[str] = []
    for value in values:
        merged.extend(normalize_items(value))
    seen: set[str] = set()
    result: list[str] = []
    for item in merged:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_officer_fields(lunar_obj: Any) -> tuple[str, str, str]:
    zhi = str(lunar_obj.getZhiXing() or "").strip()
    star = str(lunar_obj.getDayTianShen() or "").strip()
    path = str(lunar_obj.getDayTianShenType() or "").strip()
    officer = f"{zhi}日" if zhi and not zhi.endswith("日") else (zhi or "无")
    return officer, star, path


def get_hour_luck(lunar_obj: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx, time_obj in enumerate(lunar_obj.getTimes()):
        slot = HOUR_WINDOWS[idx] if idx < len(HOUR_WINDOWS) else f"时辰{idx + 1}"
        luck = str(time_obj.getTianShenLuck() or "").strip() or "无"
        rows.append({"slot": slot, "ganzhi": str(time_obj.getGanZhi()), "luck": luck})
    return rows


def format_zodiac_clash(lunar_obj: Any) -> str:
    animal = str(lunar_obj.getDayShengXiao() or "").strip()
    chong = str(lunar_obj.getDayChongShengXiao() or "").strip()
    sha = str(lunar_obj.getDaySha() or "").strip()
    head = f"{animal}日冲{chong}" if animal and chong else str(lunar_obj.getDayChongDesc() or "无")
    return f"{head}，煞{sha}" if sha else head


def format_level_fields(lunar_obj: Any) -> tuple[str, str]:
    path = str(lunar_obj.getDayTianShenType() or "").strip()
    luck = str(lunar_obj.getDayTianShenLuck() or "").strip()
    if path and luck:
        short = f"{path}{luck}"
        return short, f"{path}{luck}日"
    if luck:
        return luck, f"{luck}日"
    if path:
        return path, path
    return "平", "无特别等第"


def format_peng_taboo(lunar_obj: Any) -> str:
    parts = [
        str(lunar_obj.getPengZuGan() or "").strip(),
        str(lunar_obj.getPengZuZhi() or "").strip(),
    ]
    parts = [p for p in parts if p]
    return "；".join(parts) if parts else ""


def format_directions(lunar_obj: Any) -> list[str]:
    mapping = [
        ("喜神", lunar_obj.getDayPositionXiDesc()),
        ("财神", lunar_obj.getDayPositionCaiDesc()),
        ("福神", lunar_obj.getDayPositionFuDesc()),
        ("阳贵", lunar_obj.getDayPositionYangGuiDesc()),
        ("阴贵", lunar_obj.getDayPositionYinGuiDesc()),
    ]
    result: list[str] = []
    for label, value in mapping:
        text = str(value or "").strip()
        if text:
            result.append(f"{label}{text}")
    return result


def format_star28(lunar_obj: Any) -> str:
    xiu = str(lunar_obj.getXiu() or "").strip()
    animal = str(lunar_obj.getAnimal() or "").strip()
    luck = str(lunar_obj.getXiuLuck() or "").strip()
    core = f"{xiu}{animal}".strip()
    if not core:
        return ""
    return f"{core}（{luck}）" if luck else core


def build_result(dt: datetime) -> CalendarResult:
    solar_obj = build_solar(dt)
    lunar_obj = solar_obj.getLunar()
    officer12, day_star, day_path = get_officer_fields(lunar_obj)
    level_short, level_name = format_level_fields(lunar_obj)
    month_cn = str(lunar_obj.getMonthInChinese())
    month_label = month_cn if month_cn.endswith("月") else f"{month_cn}月"
    return CalendarResult(
        solar_date=dt.strftime("%Y-%m-%d"),
        weekday=f"星期{solar_obj.getWeekInChinese()}",
        lunar_date=f"{lunar_obj.getYearInChinese()}年 {month_label}{lunar_obj.getDayInChinese()}",
        ganzhi=(
            f"{lunar_obj.getYearInGanZhi()}年 "
            f"{lunar_obj.getMonthInGanZhi()}月 "
            f"{lunar_obj.getDayInGanZhi()}日"
        ),
        current_term=get_current_term(lunar_obj, dt),
        next_term=get_next_term(lunar_obj),
        today_term_exact=lunar_obj.getCurrentJieQi() is not None,
        holidays=get_holidays(solar_obj, lunar_obj),
        zodiac_clash=format_zodiac_clash(lunar_obj),
        officer12=officer12,
        day_star=day_star,
        day_path=day_path,
        level_name=level_name,
        level_short=level_short,
        peng_taboo=format_peng_taboo(lunar_obj),
        fetal_god=str(lunar_obj.getDayPositionTai() or "").strip(),
        directions=format_directions(lunar_obj),
        star28=format_star28(lunar_obj),
        nayin=str(lunar_obj.getDayNaYin() or "").strip(),
        good_gods=normalize_items(lunar_obj.getDayJiShen()),
        bad_gods=normalize_items(lunar_obj.getDayXiongSha()),
        good_things=normalize_items(lunar_obj.getDayYi()),
        bad_things=normalize_items(lunar_obj.getDayJi()),
        hour_luck=get_hour_luck(lunar_obj),
    )


def term_line(result: CalendarResult) -> str:
    if result.today_term_exact:
        return f"节气：{result.current_term.name}（今日交节）"
    return f"节气：当前属{result.current_term.name}；下一节气：{result.next_term.name} {result.next_term.date}"


def term_html_value(result: CalendarResult) -> str:
    if result.today_term_exact:
        return html.escape(f"{result.current_term.name}（今日交节）")
    return (
        f"当前属{html.escape(result.current_term.name)}<br>"
        f"下一节气：{html.escape(result.next_term.name)} {html.escape(result.next_term.date)}"
    )


def officer_line(result: CalendarResult) -> str:
    parts = [result.officer12]
    if result.day_star:
        parts.append(result.day_star)
    if result.day_path:
        parts.append(result.day_path)
    return " · ".join(parts)


def join_items(items: list[str]) -> str:
    return "、".join(items) if items else "无"


def luck_kind(luck: str) -> str:
    text = luck.strip()
    if text == "吉" or text.endswith("吉"):
        return "good"
    if text == "凶" or text.endswith("凶"):
        return "bad"
    return "neutral"


def render_text(result: CalendarResult) -> str:
    lines = [
        f"公历：{result.solar_date} {result.weekday}",
        f"农历：{result.lunar_date}",
        f"干支：{result.ganzhi}",
        term_line(result),
    ]
    if result.holidays:
        lines.append(f"节日：{join_items(result.holidays)}")
    lines.extend(
        [
            f"冲煞：{result.zodiac_clash}",
            f"建除十二神：{officer_line(result)}",
            f"吉凶：{result.level_short}",
        ]
    )
    if result.level_name and result.level_name not in {"无", result.level_short}:
        lines.append(f"说明：{result.level_name}")
    if result.directions:
        lines.append(f"方位：{join_items(result.directions)}")
    if result.fetal_god:
        lines.append(f"胎神：{result.fetal_god}")
    if result.peng_taboo:
        lines.append(f"彭祖百忌：{result.peng_taboo}")
    if result.nayin:
        lines.append(f"纳音：{result.nayin}")
    if result.star28:
        lines.append(f"二十八宿：{result.star28}")
    lines.extend(
        [
            f"吉神：{join_items(result.good_gods)}",
            f"凶煞：{join_items(result.bad_gods)}",
            f"宜：{join_items(result.good_things)}",
            f"忌：{join_items(result.bad_things)}",
            "时辰吉凶：",
        ]
    )
    for row in result.hour_luck:
        lines.append(f"- {row['slot']} {row['ganzhi']} {row['luck']}")
    lines.extend(["", HOUR_RULE_NOTE, SOURCE_NOTE])
    return "\n".join(lines)


def markdown_list_cell(items: list[str]) -> str:
    if not items:
        return "无"
    return "<br>".join(html.escape(item) for item in items)


def render_markdown(result: CalendarResult) -> str:
    holiday_line = f"- 节日：{join_items(result.holidays)}\n" if result.holidays else ""
    direction_line = f"- 方位：{join_items(result.directions)}\n" if result.directions else ""
    fetal_line = f"- 胎神：{result.fetal_god}\n" if result.fetal_god else ""
    peng_line = f"- 彭祖百忌：{result.peng_taboo}\n" if result.peng_taboo else ""
    nayin_line = f"- 纳音：{result.nayin}\n" if result.nayin else ""
    star_line = f"- 二十八宿：{result.star28}\n" if result.star28 else ""
    parts = [
        "# 今日黄历",
        "",
        f"- 公历：**{result.solar_date} {result.weekday}**",
        f"- 农历：**{result.lunar_date}**",
        f"- 干支：`{result.ganzhi}`",
        f"- {term_line(result)}",
        holiday_line.rstrip(),
        f"- 冲煞：{result.zodiac_clash}",
        f"- 建除十二神：{officer_line(result)}",
        f"- 吉凶：{result.level_short}",
        direction_line.rstrip(),
        fetal_line.rstrip(),
        peng_line.rstrip(),
        nayin_line.rstrip(),
        star_line.rstrip(),
        "",
        "## 宜忌",
        "",
        "| 宜 | 忌 |",
        "| --- | --- |",
        f"| {markdown_list_cell(result.good_things)} | {markdown_list_cell(result.bad_things)} |",
        "",
        "## 吉神凶煞",
        "",
        "| 吉神 | 凶煞 |",
        "| --- | --- |",
        f"| {markdown_list_cell(result.good_gods)} | {markdown_list_cell(result.bad_gods)} |",
        "",
        "## 时辰吉凶",
        "",
        "| 时段 | 时辰 | 吉凶 |",
        "| --- | --- | --- |",
    ]
    for row in result.hour_luck:
        parts.append(f"| {row['slot']} | {row['ganzhi']} | {row['luck']} |")
    parts.extend(["", f"> {HOUR_RULE_NOTE}", f"> {SOURCE_NOTE}"])
    return "\n".join(line for line in parts if line is not None).strip() + "\n"


def render_badges(items: list[str], kind: str) -> str:
    if not items:
        return (
            f'<span style="display:inline-block;margin:0 8px 8px 0;padding:6px 10px;'
            f"border-radius:999px;font-size:13px;line-height:1.4;background:#F5EFE7;"
            f'color:#7A6C66;border:1px solid #E7DDD1;font-family:{FONT_SANS};">无</span>'
        )
    palette = {
        "good": ("#F0F5F1", "#4E7A5A", "#DBE8DF"),
        "bad": ("#FAF1F0", "#9B3D3D", "#EFD6D2"),
        "info": ("#F8F3EA", "#6E6158", "#E9DDD0"),
        "warn": ("#F8EFE7", "#8A5D4D", "#EAD8C9"),
    }
    bg, color, border = palette.get(kind, palette["info"])
    return "".join(
        (
            f'<span style="display:inline-block;margin:0 8px 8px 0;padding:6px 10px;'
            f"border-radius:999px;font-size:13px;line-height:1.4;background:{bg};"
            f"color:{color};border:1px solid {border};max-width:100%;"
            f'word-break:break-word;font-family:{FONT_SANS};">{html.escape(item)}</span>'
        )
        for item in items
    )


def render_dense_lines(items: list[str], chunk: int = 8) -> str:
    if not items:
        return "无"
    escaped = [html.escape(item) for item in items]
    lines = ["、".join(escaped[i : i + chunk]) for i in range(0, len(escaped), chunk)]
    return "<br>".join(lines)


def email_spacer(height: int = 16) -> str:
    return (
        f'<tr><td height="{height}" style="height:{height}px;line-height:{height}px;'
        f'font-size:0;">&nbsp;</td></tr>'
    )


def email_section_inner(
    title: str,
    body_html: str,
    head_bg: str,
    head_color: str,
    *,
    head_radius: str = "16px 16px 0 0",
) -> str:
    # Content only. Outer card/pair shell owns the full border + outer radius.
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;border-collapse:collapse;">
  <tr>
    <td bgcolor="{head_bg}" style="padding:12px 16px;background:{head_bg};color:{head_color};
      font-size:16px;font-weight:700;font-family:{FONT_SANS};border-bottom:1px solid #EFE6DA;
      border-radius:{head_radius};">
      {html.escape(title)}
    </td>
  </tr>
  <tr>
    <td style="padding:16px;font-family:{FONT_SANS};color:#3E3836;font-size:14px;line-height:1.75;
      word-break:break-word;">
      {body_html}
    </td>
  </tr>
</table>
"""


def email_section_card(title: str, body_html: str, head_bg: str, head_color: str) -> str:
    # Full-width single card; outer table owns border + radius for consistent width.
    radius = 16
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  bgcolor="#FFFFFF"
  style="width:100%;border-collapse:separate;background:#FFFFFF;border:1px solid #ECE3D6;
  border-radius:{radius}px;">
  <tr>
    <td style="padding:0;border-radius:{radius}px;">
      {email_section_inner(title, body_html, head_bg, head_color, head_radius=f"{radius}px {radius}px 0 0")}
    </td>
  </tr>
</table>
"""


def email_pair_cells(left_inner: str, right_inner: str, *, radius: int = 16) -> str:
    """Two separate equal-height cards, outer edges aligned with full-width cards.

    Gmail-safe pattern:
    - TWO independent cards (each TD has its own border + radius), not one shell.
    - Same table row => both card cells stretch to equal height.
    - Fixed layout + 49% / 2% / 49% keeps total width = 100% (no border-spacing inset).
    - Middle column is only a visual gap, not a divider line inside one card.
    """
    card_style = (
        f"vertical-align:top;background:#FFFFFF;padding:0;"
        f"border:1px solid #ECE3D6;border-radius:{radius}px;"
    )
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;border-collapse:separate;border-spacing:0;table-layout:fixed;">
  <tr>
    <td width="49%" valign="top" bgcolor="#FFFFFF"
      style="width:49%;{card_style}">
      {left_inner}
    </td>
    <td width="2%" aria-hidden="true"
      style="width:2%;padding:0;margin:0;font-size:0;line-height:0;border:0;">&nbsp;</td>
    <td width="49%" valign="top" bgcolor="#FFFFFF"
      style="width:49%;{card_style}">
      {right_inner}
    </td>
  </tr>
</table>
"""


def email_mini_inner(label: str, value_html: str) -> str:
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;border-collapse:collapse;">
  <tr>
    <td valign="top" style="padding:14px 16px;font-family:{FONT_SANS};vertical-align:top;">
      <div style="color:#7A6C66;font-size:13px;margin:0 0 6px;font-family:{FONT_SANS};">{html.escape(label)}</div>
      <div style="color:#3E3836;font-size:15px;font-weight:600;line-height:1.55;font-family:{FONT_SANS};
        word-break:break-word;">{value_html}</div>
    </td>
  </tr>
</table>
"""



def email_kv_row(label: str, value_html: str, *, last: bool = False) -> str:
    border = "0" if last else "1px solid #EFE6DA"
    return f"""
<tr>
  <td width="26%" valign="top"
    style="width:26%;padding:9px 0;border-bottom:{border};color:#8D7F77;font-size:13px;
    line-height:1.5;font-family:{FONT_SANS};vertical-align:top;white-space:nowrap;">
    {html.escape(label)}
  </td>
  <td width="74%" valign="top"
    style="width:74%;padding:9px 0 9px 12px;border-bottom:{border};color:#3E3836;font-size:14px;
    line-height:1.55;font-weight:600;font-family:{FONT_SANS};vertical-align:top;word-break:break-word;">
    {value_html}
  </td>
</tr>
"""


def email_kv_table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    body = "".join(
        email_kv_row(label, value_html, last=(idx == len(rows) - 1))
        for idx, (label, value_html) in enumerate(rows)
    )
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;border-collapse:collapse;margin-top:4px;">
  {body}
</table>
"""


def email_chip(text: str, *, bg: str, color: str, border: str) -> str:
    return (
        f'<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;'
        f"border-radius:999px;font-size:12px;line-height:1.4;background:{bg};"
        f"color:{color};border:1px solid {border};font-family:{FONT_SANS};"
        f'font-weight:600;">{html.escape(text)}</span>'
    )


def render_direction_chips(items: list[str]) -> str:
    if not items:
        return "无"
    return "".join(
        email_chip(item, bg="#F8F3EA", color="#6E6158", border="#E9DDD0") for item in items
    )


def render_html(result: CalendarResult) -> str:
    holiday_value = html.escape(join_items(result.holidays)) if result.holidays else "今日无特别节日"
    preheader = (
        f"{result.solar_date} {result.weekday} · {result.lunar_date} · "
        f"{result.level_short} · {officer_line(result)}"
    )
    path_is_good = "黄道" in (result.day_path or "") or "吉" in (result.level_short or "")
    path_bg = "#F0F5F1" if path_is_good else "#FAF1F0"
    path_color = "#4E7A5A" if path_is_good else "#9B3D3D"
    path_border = "#DBE8DF" if path_is_good else "#EFD6D2"

    # 徽章：黄道/黑道 + 吉/凶；避免与下方「建除/说明」重复堆叠
    badges: list[str] = []
    if result.day_path:
        badges.append(
            email_chip(result.day_path, bg=path_bg, color=path_color, border=path_border)
        )
    luck_text = (result.level_short or "").replace("黄道", "").replace("黑道", "").strip() or result.level_short
    if luck_text and luck_text not in {result.day_path, ""}:
        luck_good = "吉" in luck_text and "凶" not in luck_text
        badges.append(
            email_chip(
                luck_text,
                bg="#F0F5F1" if luck_good else "#FAF1F0",
                color="#4E7A5A" if luck_good else "#9B3D3D",
                border="#DBE8DF" if luck_good else "#EFD6D2",
            )
        )
    if result.officer12:
        badges.append(
            email_chip(result.officer12, bg="#F8F3EA", color="#6E6158", border="#E9DDD0")
        )
    if result.day_star:
        badges.append(
            email_chip(result.day_star, bg="#F8F3EA", color="#6E6158", border="#E9DDD0")
        )
    badge_html = "".join(badges) if badges else email_chip(result.level_short or "平", bg=path_bg, color=path_color, border=path_border)

    primary_rows: list[tuple[str, str]] = [
        ("干支", html.escape(result.ganzhi)),
        ("冲煞", html.escape(result.zodiac_clash)),
    ]
    secondary_rows: list[tuple[str, str]] = []
    if result.directions:
        secondary_rows.append(("方位", render_direction_chips(result.directions)))
    if result.fetal_god:
        secondary_rows.append(("胎神", html.escape(result.fetal_god)))
    if result.peng_taboo:
        # 彭祖两句换行，避免超长一行
        peng = "；".join(part.strip() for part in result.peng_taboo.split("；") if part.strip())
        peng_html = "<br>".join(html.escape(p) for p in peng.split("；"))
        secondary_rows.append(("彭祖百忌", peng_html))
    if result.nayin:
        secondary_rows.append(("纳音", html.escape(result.nayin)))
    if result.star28:
        secondary_rows.append(("二十八宿", html.escape(result.star28)))

    meta_html = email_kv_table(primary_rows)
    if secondary_rows:
        meta_html += (
            '<div style="height:10px;line-height:10px;font-size:0;border-top:1px dashed #E7DDD1;'
            'margin-top:4px;">&nbsp;</div>'
            + email_kv_table(secondary_rows)
        )

    good_body = (
        f'<div style="color:#4E7A5A;font-size:14px;line-height:1.8;font-weight:500;'
        f'font-family:{FONT_SANS};">{render_dense_lines(result.good_things)}</div>'
    )
    bad_body = (
        f'<div style="color:#9B3D3D;font-size:14px;line-height:1.8;font-weight:500;'
        f'font-family:{FONT_SANS};">{render_dense_lines(result.bad_things)}</div>'
    )
    term_holiday = email_pair_cells(
        email_mini_inner("节气", term_html_value(result)),
        email_mini_inner("节日", holiday_value),
    )
    gods_pair = email_pair_cells(
        email_section_inner(
            "吉神",
            render_badges(result.good_gods, "info"),
            "#F8F3EA",
            "#6E6158",
            head_radius="15px 15px 0 0",
        ),
        email_section_inner(
            "凶煞",
            render_badges(result.bad_gods, "warn"),
            "#F7EFE8",
            "#8A5D4D",
            head_radius="15px 15px 0 0",
        ),
    )
    yi_ji = (
        email_section_card("宜", good_body, "#F0F5F1", "#4E7A5A")
        + '<div style="height:12px;line-height:12px;font-size:0;">&nbsp;</div>'
        + email_section_card("忌", bad_body, "#FAF1F0", "#9B3D3D")
    )

    hour_rows = []
    for row in result.hour_luck:
        kind = luck_kind(row["luck"])
        if kind == "good":
            luck_style = "background:#F0F5F1;color:#4E7A5A;"
        elif kind == "bad":
            luck_style = "background:#FAF1F0;color:#9B3D3D;"
        else:
            luck_style = "background:#F5EFE7;color:#7A6C66;"
        hour_rows.append(
            f"""
            <tr>
              <td width="42%" style="padding:11px 12px;border-bottom:1px solid #EFE6DA;
                font-family:{FONT_SANS};color:#3E3836;font-size:14px;">{html.escape(row['slot'])}</td>
              <td width="33%" style="padding:11px 12px;border-bottom:1px solid #EFE6DA;
                font-family:{FONT_SANS};color:#3E3836;font-size:14px;">{html.escape(row['ganzhi'])}</td>
              <td width="25%" style="padding:11px 12px;border-bottom:1px solid #EFE6DA;
                font-family:{FONT_SANS};color:#3E3836;font-size:14px;">
                <span style="display:inline-block;min-width:42px;text-align:center;padding:4px 10px;
                  border-radius:999px;font-weight:700;{luck_style}">{html.escape(row['luck'])}</span>
              </td>
            </tr>
            """
        )
    hour_rows_html = "".join(hour_rows)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="x-ua-compatible" content="ie=edge" />
  <title>今日黄历</title>
  <!--[if mso]>
  <style type="text/css">
    table, td, div, span, p {{ font-family: Arial, sans-serif !important; }}
  </style>
  <![endif]-->
</head>
<body style="margin:0;padding:0;background:#FFFFFF;color:#3E3836;font-size:15px;line-height:1.7;
  font-family:{FONT_SANS};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;
    overflow:hidden;mso-hide:all;">
    {html.escape(preheader)}
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
    style="width:100%;background:#FFFFFF;border-collapse:collapse;">
    <tr>
      <td align="center" style="padding:20px 12px;background:#FFFFFF;">
        <table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0"
          style="width:100%;max-width:640px;border-collapse:collapse;">
          <tr>
            <td>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="#FDF9F1"
                style="width:100%;background:#FDF9F1;border:1px solid #EADFCE;border-collapse:separate;
                border-radius:18px;overflow:hidden;">
                <tr>
                  <td style="padding:22px 20px;font-family:{FONT_SANS};border-radius:18px;">
                    <div style="margin:0;font-size:22px;line-height:1.3;font-weight:600;color:#3E3836;
                      font-family:{FONT_SANS};">
                      {html.escape(result.solar_date)} {html.escape(result.weekday)}
                    </div>
                    <div style="margin:8px 0 0;font-size:26px;line-height:1.35;font-weight:700;
                      letter-spacing:0.02em;color:#9B3D3D;font-family:{FONT_SERIF};">
                      {html.escape(result.lunar_date)}
                    </div>
                    <div style="margin-top:14px;line-height:1.2;">
                      {badge_html}
                    </div>
                    <div style="margin-top:8px;">
                      {meta_html}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          {email_spacer(14)}

          <tr>
            <td>
              {term_holiday}
            </td>
          </tr>

          {email_spacer(14)}

          <tr>
            <td>
              {yi_ji}
            </td>
          </tr>

          {email_spacer(14)}

          <tr>
            <td>
              {gods_pair}
            </td>
          </tr>

          {email_spacer(18)}

          <tr>
            <td style="font-size:17px;font-weight:700;color:#3E3836;font-family:{FONT_SANS};
              padding:0 0 10px;">
              时辰吉凶
            </td>
          </tr>
          <tr>
            <td>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                style="width:100%;background:#FFFFFF;border:1px solid #ECE3D6;border-collapse:separate;
                border-radius:16px;overflow:hidden;">
                <tr>
                  <th align="left" width="42%" bgcolor="#F8F4EE"
                    style="padding:11px 12px;background:#F8F4EE;color:#7A6C66;font-size:13px;
                    font-weight:600;font-family:{FONT_SANS};border-bottom:1px solid #EFE6DA;text-align:left;">
                    时段
                  </th>
                  <th align="left" width="33%" bgcolor="#F8F4EE"
                    style="padding:11px 12px;background:#F8F4EE;color:#7A6C66;font-size:13px;
                    font-weight:600;font-family:{FONT_SANS};border-bottom:1px solid #EFE6DA;text-align:left;">
                    时辰
                  </th>
                  <th align="left" width="25%" bgcolor="#F8F4EE"
                    style="padding:11px 12px;background:#F8F4EE;color:#7A6C66;font-size:13px;
                    font-weight:600;font-family:{FONT_SANS};border-bottom:1px solid #EFE6DA;text-align:left;">
                    吉凶
                  </th>
                </tr>
                {hour_rows_html}
              </table>
            </td>
          </tr>

          <tr>
            <td style="color:#8D7F77;font-size:12px;text-align:center;padding:16px 0 4px;
              font-family:{FONT_SANS};">
              Generated with lunar-python · {html.escape(SOURCE_NOTE)} · {TIMEZONE_NAME}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def auto_detect_smtp(from_email: str, smtp_server: str, smtp_port: str) -> tuple[str, int]:
    server = smtp_server.strip()
    port = smtp_port.strip()
    if server and port:
        return server, int(port)
    if server or port:
        raise SystemExit("EMAIL_SMTP_SERVER 和 EMAIL_SMTP_PORT 需要同时填写，或同时留空")

    domain = from_email.split("@")[-1].lower()
    mapping = {
        "gmail.com": ("smtp.gmail.com", 587),
        "googlemail.com": ("smtp.gmail.com", 587),
        "qq.com": ("smtp.qq.com", 587),
        "163.com": ("smtp.163.com", 465),
        "vip.163.com": ("smtp.163.com", 465),
        "126.com": ("smtp.126.com", 465),
        "yeah.net": ("smtp.yeah.net", 465),
        "outlook.com": ("smtp-mail.outlook.com", 587),
        "hotmail.com": ("smtp-mail.outlook.com", 587),
    }
    if domain not in mapping:
        raise SystemExit("无法自动识别 SMTP，请设置 EMAIL_SMTP_SERVER 和 EMAIL_SMTP_PORT")
    return mapping[domain]


def send_email(report: RenderedReport) -> None:
    from_email = os.getenv("EMAIL_FROM", "").strip()
    password = os.getenv("EMAIL_PASSWORD", "").replace(" ", "").strip()
    to_email = os.getenv("EMAIL_TO", "").strip()
    from_name = os.getenv("EMAIL_FROM_NAME", "今日黄历").strip() or "今日黄历"
    smtp_server, smtp_port = auto_detect_smtp(
        from_email,
        os.getenv("EMAIL_SMTP_SERVER", ""),
        os.getenv("EMAIL_SMTP_PORT", ""),
    )

    missing = [
        name for name, value in {
            "EMAIL_FROM": from_email,
            "EMAIL_PASSWORD": password,
            "EMAIL_TO": to_email,
        }.items() if not value
    ]
    if missing:
        raise SystemExit(f"缺少邮件环境变量: {', '.join(missing)}")

    msg = EmailMessage()
    msg["Subject"] = report.subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg.set_content(report.text)
    msg.add_alternative(report.html, subtype="html")

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as smtp:
            smtp.login(from_email, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(from_email, password)
            smtp.send_message(msg)


def build_report(result: CalendarResult) -> RenderedReport:
    subject_prefix = os.getenv("EMAIL_SUBJECT_PREFIX", "").strip()
    subject = f"今日黄历 · {result.solar_date} · {result.weekday}"
    if subject_prefix:
        subject = f"{subject_prefix} {subject}"
    return RenderedReport(
        subject=subject,
        text=render_text(result),
        markdown=render_markdown(result),
        html=render_html(result),
    )


def save_report(report: RenderedReport, save_dir: str) -> None:
    dist = Path(save_dir)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "today.txt").write_text(report.text + "\n", encoding="utf-8")
    (dist / "today.md").write_text(report.markdown, encoding="utf-8")
    (dist / "today.html").write_text(report.html, encoding="utf-8")


def resolve_save_dir(raw: str | None) -> str | None:
    if raw is None:
        return "dist"
    value = raw.strip()
    if not value or value.lower() in {"none", "-", "/dev/null"}:
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and optionally email the daily Chinese almanac")
    parser.add_argument("--date", help="可选日期，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")
    parser.add_argument("--send-email", action="store_true", help="发送 HTML 邮件")
    parser.add_argument("--save-dir", default="dist", help="输出目录，默认 dist；none/- 表示不保存")
    parser.add_argument(
        "--stdout-format",
        choices=["text", "markdown"],
        default="text",
        help="控制台输出格式",
    )
    args = parser.parse_args()

    result = build_result(parse_target_datetime(args.date))
    report = build_report(result)
    save_dir = resolve_save_dir(args.save_dir)
    if save_dir:
        save_report(report, save_dir)
    if args.send_email:
        send_email(report)

    if args.stdout_format == "markdown":
        print(report.markdown, end="")
    else:
        print(report.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
