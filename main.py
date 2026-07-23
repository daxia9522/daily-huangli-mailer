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

import cnlunar

TIMEZONE_NAME = "Asia/Shanghai"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)
HOUR_WINDOWS = [
    "23:00-00:59",
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
]
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
    fetal_god: str
    directions: list[str]
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


def build_lunar(dt: datetime):
    return cnlunar.Lunar(dt.replace(tzinfo=None))


def get_current_term(lunar_obj: Any, dt: datetime) -> TermInfo:
    current_key = (dt.month, dt.day)
    this_year_terms = sorted(lunar_obj.thisYearSolarTermsDic.items(), key=lambda item: item[1])
    candidates = [(name, md) for name, md in this_year_terms if md <= current_key]
    if candidates:
        name, (month, day) = candidates[-1]
        return TermInfo(name=name, date=f"{dt.year:04d}-{month:02d}-{day:02d}")

    prev = build_lunar(datetime(dt.year - 1, 12, 31, 12, 0, tzinfo=dt.tzinfo))
    prev_terms = sorted(prev.thisYearSolarTermsDic.items(), key=lambda item: item[1])
    name, (month, day) = prev_terms[-1]
    return TermInfo(name=name, date=f"{dt.year - 1:04d}-{month:02d}-{day:02d}")


def get_next_term(lunar_obj: Any) -> TermInfo:
    year = lunar_obj.nextSolarTermYear
    month, day = lunar_obj.nextSolarTermDate
    return TermInfo(name=lunar_obj.nextSolarTerm, date=f"{year:04d}-{month:02d}-{day:02d}")


def get_holidays(lunar_obj: Any) -> list[str]:
    values = [
        lunar_obj.get_legalHolidays(),
        lunar_obj.get_otherHolidays(),
        lunar_obj.get_otherLunarHolidays(),
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
    info = lunar_obj.get_today12DayOfficer()
    if isinstance(info, (list, tuple)) and len(info) >= 3:
        return f"{info[0]}日", str(info[1]), str(info[2])
    return f"{lunar_obj.today12DayOfficer}日", "", ""


def get_hour_luck(lunar_obj: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    branches = list(lunar_obj.twohour8CharList[:12])
    lucky = list(lunar_obj.get_twohourLuckyList()[:12])
    for idx, (ganzhi, state) in enumerate(zip(branches, lucky, strict=False)):
        rows.append({"slot": HOUR_WINDOWS[idx], "ganzhi": str(ganzhi), "luck": str(state)})
    return rows


def build_result(dt: datetime) -> CalendarResult:
    lunar_obj = build_lunar(dt)
    officer12, day_star, day_path = get_officer_fields(lunar_obj)
    level_name = str(lunar_obj.todayLevelName)
    level_short = str(getattr(lunar_obj, "thingLevelName", "") or "").strip() or level_name
    return CalendarResult(
        solar_date=dt.strftime("%Y-%m-%d"),
        weekday=str(lunar_obj.weekDayCn),
        lunar_date=f"{lunar_obj.lunarYearCn}年 {lunar_obj.lunarMonthCn}{lunar_obj.lunarDayCn}",
        ganzhi=f"{lunar_obj.year8Char}年 {lunar_obj.month8Char}月 {lunar_obj.day8Char}日",
        current_term=get_current_term(lunar_obj, dt),
        next_term=get_next_term(lunar_obj),
        today_term_exact=(str(lunar_obj.todaySolarTerms) != "无"),
        holidays=get_holidays(lunar_obj),
        zodiac_clash=str(lunar_obj.chineseZodiacClash),
        officer12=officer12,
        day_star=day_star,
        day_path=day_path,
        level_name=level_name,
        level_short=level_short,
        fetal_god=str(lunar_obj.get_fetalGod() or "").strip(),
        directions=normalize_items(lunar_obj.get_luckyGodsDirection()),
        good_gods=normalize_items(lunar_obj.goodGodName),
        bad_gods=normalize_items(lunar_obj.badGodName),
        good_things=normalize_items(lunar_obj.goodThing),
        bad_things=normalize_items(lunar_obj.badThing),
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
    return "\n".join(lines)


def markdown_list_cell(items: list[str]) -> str:
    if not items:
        return "无"
    return "<br>".join(html.escape(item) for item in items)


def render_markdown(result: CalendarResult) -> str:
    holiday_line = f"- 节日：{join_items(result.holidays)}\n" if result.holidays else ""
    direction_line = f"- 方位：{join_items(result.directions)}\n" if result.directions else ""
    fetal_line = f"- 胎神：{result.fetal_god}\n" if result.fetal_god else ""
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


def email_section_inner(title: str, body_html: str, head_bg: str, head_color: str, radius: int = 16) -> str:
    # No outer border here — caller paints border on the stretching cell.
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;border-collapse:separate;">
  <tr>
    <td bgcolor="{head_bg}" style="padding:12px 16px;background:{head_bg};color:{head_color};
      font-size:16px;font-weight:700;font-family:{FONT_SANS};border-bottom:1px solid #EFE6DA;
      border-radius:{radius}px {radius}px 0 0;">
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
    # Full-width single card with its own rounded border.
    radius = 16
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;border-collapse:separate;background:#FFFFFF;border:1px solid #ECE3D6;
  border-radius:{radius}px;overflow:hidden;">
  <tr>
    <td style="padding:0;border-radius:{radius}px;overflow:hidden;">
      {email_section_inner(title, body_html, head_bg, head_color, radius=radius)}
    </td>
  </tr>
</table>
"""


def email_pair_cells(left_inner: str, right_inner: str, *, radius: int = 16) -> str:
    """Equal-height dual cards: border/radius on the same-row outer tds.

    Table row cells stretch to the taller sibling, so both chrome boxes match height
    even when content length differs (节气 vs 节日, 吉神 vs 凶煞).
    """
    cell_style = (
        f"width:50%;vertical-align:top;background:#FFFFFF;border:1px solid #ECE3D6;"
        f"border-radius:{radius}px;overflow:hidden;"
    )
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;border-collapse:separate;border-spacing:0;">
  <tr>
    <td width="50%" valign="top" bgcolor="#FFFFFF"
      style="{cell_style}padding:0;">
      {left_inner}
    </td>
    <td width="12" style="width:12px;font-size:0;line-height:0;">&nbsp;</td>
    <td width="50%" valign="top" bgcolor="#FFFFFF"
      style="{cell_style}padding:0;">
      {right_inner}
    </td>
  </tr>
</table>
"""


def email_mini_inner(label: str, value_html: str) -> str:
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;">
  <tr>
    <td style="padding:14px 16px;font-family:{FONT_SANS};">
      <div style="color:#7A6C66;font-size:13px;margin:0 0 6px;font-family:{FONT_SANS};">{html.escape(label)}</div>
      <div style="color:#3E3836;font-size:15px;font-weight:600;line-height:1.55;font-family:{FONT_SANS};
        word-break:break-word;">{value_html}</div>
    </td>
  </tr>
</table>
"""


def render_html(result: CalendarResult) -> str:
    holiday_value = html.escape(join_items(result.holidays)) if result.holidays else "今日无特别节日"
    preheader = (
        f"{result.solar_date} {result.weekday} · {result.lunar_date} · "
        f"{result.level_short} · {officer_line(result)}"
    )
    path_badge = html.escape(result.day_path or result.level_short)
    path_is_good = "黄道" in (result.day_path or "")
    path_bg = "#F0F5F1" if path_is_good else "#FAF1F0"
    path_color = "#4E7A5A" if path_is_good else "#9B3D3D"

    meta_lines = [
        f"干支：{html.escape(result.ganzhi)}",
        f"冲煞：{html.escape(result.zodiac_clash)}",
        f"建除：{html.escape(officer_line(result))}",
        f"吉凶：{html.escape(result.level_short)}",
    ]
    if result.level_name and result.level_name not in {"无", result.level_short}:
        meta_lines.append(f"说明：{html.escape(result.level_name)}")
    if result.directions:
        meta_lines.append(f"方位：{html.escape(join_items(result.directions))}")
    if result.fetal_god:
        meta_lines.append(f"胎神：{html.escape(result.fetal_god)}")

    meta_html = "".join(
        (
            f'<div style="margin-top:4px;font-size:15px;font-weight:500;line-height:1.5;'
            f'color:#7A6C66;font-family:{FONT_SANS};word-break:break-word;">{line}</div>'
        )
        for line in meta_lines
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
        email_section_inner("吉神", render_badges(result.good_gods, "info"), "#F8F3EA", "#6E6158"),
        email_section_inner("凶煞", render_badges(result.bad_gods, "warn"), "#F7EFE8", "#8A5D4D"),
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
                    <div style="margin-top:12px;">
                      <span style="display:inline-block;padding:5px 12px;border-radius:999px;
                        background:{path_bg};color:{path_color};font-size:13px;font-weight:700;
                        font-family:{FONT_SANS};">{path_badge}</span>
                    </div>
                    <div style="margin-top:10px;">
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
              Generated with cnlunar · Timezone: {TIMEZONE_NAME}
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and optionally email the daily Chinese almanac")
    parser.add_argument("--date", help="可选日期，支持 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")
    parser.add_argument("--send-email", action="store_true", help="发送 HTML 邮件")
    parser.add_argument("--save-dir", default="dist", help="输出目录，默认 dist；传空字符串则不保存")
    parser.add_argument(
        "--stdout-format",
        choices=["text", "markdown"],
        default="text",
        help="控制台输出格式",
    )
    args = parser.parse_args()

    result = build_result(parse_target_datetime(args.date))
    report = build_report(result)
    if args.save_dir:
        save_report(report, args.save_dir)
    if args.send_email:
        send_email(report)

    if args.stdout_format == "markdown":
        print(report.markdown, end="")
    else:
        print(report.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
