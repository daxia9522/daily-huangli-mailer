#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
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
    level_name: str
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
    for sep in ["、", "，", ",", " "]:
        if sep in raw and len(raw) > 1:
            parts = [part.strip() for part in raw.split(sep) if part.strip()]
            if len(parts) > 1:
                return parts
    return [raw]


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


def get_hour_luck(lunar_obj: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    branches = list(lunar_obj.twohour8CharList[:12])
    lucky = list(lunar_obj.get_twohourLuckyList()[:12])
    for idx, (ganzhi, state) in enumerate(zip(branches, lucky, strict=False)):
        rows.append({"slot": HOUR_WINDOWS[idx], "ganzhi": str(ganzhi), "luck": str(state)})
    return rows


def build_result(dt: datetime) -> CalendarResult:
    lunar_obj = build_lunar(dt)
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
        officer12=f"{lunar_obj.today12DayOfficer}日",
        level_name=str(lunar_obj.todayLevelName),
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


def join_items(items: list[str]) -> str:
    return "、".join(items) if items else "无"


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
            f"建除十二神：{result.officer12}",
            f"吉凶等级：{result.level_name}",
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
    parts = [
        "# 今日黄历",
        "",
        f"- 公历：**{result.solar_date} {result.weekday}**",
        f"- 农历：**{result.lunar_date}**",
        f"- 干支：`{result.ganzhi}`",
        f"- {term_line(result)}",
        holiday_line.rstrip(),
        f"- 冲煞：{result.zodiac_clash}",
        f"- 建除十二神：{result.officer12}",
        f"- 吉凶等级：{result.level_name}",
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
        return '<span class="tag tag-muted">无</span>'
    return "".join(
        f'<span class="tag tag-{kind}">{html.escape(item)}</span>' for item in items
    )


def render_dense_lines(items: list[str], chunk: int = 8) -> str:
    if not items:
        return "无"
    escaped = [html.escape(item) for item in items]
    lines = ["、".join(escaped[i:i + chunk]) for i in range(0, len(escaped), chunk)]
    return "<br>".join(lines)


def render_html(result: CalendarResult) -> str:
    holiday_value = html.escape(join_items(result.holidays)) if result.holidays else "今日无特别节日"
    term_value = html.escape(term_line(result)).replace("；", "；<br>")

    hour_rows = "".join(
        f"""
        <tr>
          <td>{html.escape(row['slot'])}</td>
          <td>{html.escape(row['ganzhi'])}</td>
          <td><span class="luck {'good' if row['luck'] == '吉' else 'bad'}">{html.escape(row['luck'])}</span></td>
        </tr>
        """
        for row in result.hour_luck
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>今日黄历</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background: #fdf9f1;
      color: #3e3836;
      font-size: 15px;
      line-height: 1.7;
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
    }}
    body, table, td, div, p, span, a {{
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
    }}
    table {{ border-collapse: collapse; border-spacing: 0; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    .page {{ width: 100%; background: #fdf9f1; padding: 24px 0; }}
    .container {{ width: 100%; max-width: 860px; margin: 0 auto; }}
    .hero {{
      background: #fdf9f1;
      background-image: linear-gradient(135deg, #fdf9f1 0%, #f7efe2 56%, #f3eadf 100%);
      border: 1px solid #eadfce;
      border-radius: 22px;
      overflow: hidden;
      color: #3e3836;
      box-shadow: 0 12px 30px rgba(110, 84, 58, 0.10);
    }}
    .hero-inner {{
      padding: 24px;
      background-color: rgba(255,255,255,0.24);
    }}
    .hero-main {{
      margin: 0;
      font-size: 24px;
      line-height: 1.25;
      font-weight: 600;
      color: #3e3836;
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
      text-shadow: 0 1px 0 rgba(255,255,255,0.42);
    }}
    .hero-sub {{
      margin: 6px 0 0;
      font-size: 28px;
      line-height: 1.3;
      font-weight: 700;
      letter-spacing: 0.02em;
      color: #9b3d3d;
      font-family: 'Songti SC', 'STSong', 'SimSun', 'Noto Serif CJK SC', 'Noto Serif SC', serif;
      text-shadow: 0 1px 0 rgba(255,255,255,0.42);
    }}
    .meta-lines {{ margin-top: 10px; }}
    .meta-line {{
      margin-top: 4px;
      font-size: 16px;
      font-weight: 500;
      line-height: 1.45;
      color: #7a6c66;
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .spacer {{ height: 16px; line-height: 16px; }}
    .card {{
      background: #ffffff;
      border: 1px solid #ece3d6;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 10px 28px rgba(92, 71, 52, 0.08);
    }}
    .card-inner {{
      padding: 18px;
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .label {{ color: #7a6c66; font-size: 13px; margin-bottom: 6px; font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif; }}
    .value {{
      font-size: 16px;
      font-weight: 600;
      color: #3e3836;
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
      line-height: 1.55;
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .pair-table {{
      width: 100%;
      table-layout: fixed;
      border-collapse: separate;
      border-spacing: 0;
    }}
    .pair-grid {{
      width: 100%;
      table-layout: fixed;
      border-collapse: separate;
      border-spacing: 0;
    }}
    .pair-col {{
      vertical-align: top;
      background: #ffffff;
      border: 1px solid #ece3d6;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 10px 28px rgba(92, 71, 52, 0.08);
    }}
    .pair-gap {{
      width: 14px;
      font-size: 0;
      line-height: 0;
    }}
    .pair-card,
    .pair-panel {{
      width: 100%;
      box-sizing: border-box;
      border-collapse: separate;
      border-spacing: 0;
      background: #ffffff;
      border: 1px solid #ece3d6;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 10px 28px rgba(92, 71, 52, 0.08);
    }}
    .pair-panel-inner {{
      padding: 18px;
      vertical-align: top;
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .pair-head {{
      padding: 12px 16px;
      font-size: 16px;
      font-weight: 700;
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
      border-bottom: 1px solid #efe6da;
    }}
    .pair-head.good {{ background: #f0f5f1; color: #4e7a5a; }}
    .pair-head.bad {{ background: #faf1f0; color: #9b3d3d; }}
    .pair-head.info {{ background: #f8f3ea; color: #6e6158; }}
    .pair-head.warn {{ background: #f7efe8; color: #8a5d4d; }}
    .pair-body {{
      padding: 16px;
      vertical-align: top;
      overflow: hidden;
    }}
    .dense-list {{
      font-size: 14px;
      line-height: 1.75;
      word-break: break-word;
      font-weight: 500;
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
    }}
    .dense-list.good {{ color: #4e7a5a; }}
    .dense-list.bad {{ color: #9b3d3d; }}
    .tags {{ font-size: 0; }}
    .tag {{
      display: inline-block;
      margin: 0 8px 8px 0;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 13px;
      line-height: 1.4;
      border: 1px solid transparent;
      max-width: 100%;
      white-space: normal;
      word-break: break-word;
      overflow-wrap: anywhere;
      font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif;
    }}
    .tag-good {{ background: #f0f5f1; color: #4e7a5a; border-color: #dbe8df; }}
    .tag-bad {{ background: #faf1f0; color: #9b3d3d; border-color: #efd6d2; }}
    .tag-info {{ background: #f8f3ea; color: #6e6158; border-color: #e9ddd0; }}
    .tag-warn {{ background: #f8efe7; color: #8a5d4d; border-color: #ead8c9; }}
    .tag-muted {{ background: #f5efe7; color: #7a6c66; border-color: #e7ddd1; }}
    .section-title {{ font-size: 18px; font-weight: 700; color: #3e3836; margin: 0 0 12px; font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif; }}
    .time-table {{
      width: 100%;
      background: #ffffff;
      border: 1px solid #ece3d6;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 10px 28px rgba(92, 71, 52, 0.08);
    }}
    .time-table th,
    .time-table td {{ padding: 12px 14px; border-bottom: 1px solid #efe6da; text-align: left; font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif; color: #3e3836; }}
    .time-table th {{ background: #f8f4ee; color: #7a6c66; font-size: 13px; font-weight: 600; }}
    .time-table tr:last-child td {{ border-bottom: none; }}
    .luck {{ display: inline-block; min-width: 42px; text-align: center; padding: 4px 10px; border-radius: 999px; font-weight: 700; }}
    .luck.good {{ background: #f0f5f1; color: #4e7a5a; }}
    .luck.bad {{ background: #faf1f0; color: #9b3d3d; }}
    .footer {{ color: #8d7f77; font-size: 12px; text-align: center; padding: 10px 0 0; font-family: 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', Arial, sans-serif; }}

    @media only screen and (max-width: 700px) {{
      .page {{ padding: 12px 0 !important; }}
      .hero-inner {{ padding: 18px !important; }}
      .hero-main {{ font-size: 20px !important; }}
      .hero-sub {{ font-size: 24px !important; line-height: 1.28 !important; }}
      .meta-line {{ font-size: 15px !important; }}
      .pair-grid.mobile-stack,
      .pair-grid.mobile-stack tbody,
      .pair-grid.mobile-stack tr,
      .pair-grid.mobile-stack td {{
        display: block !important;
        width: 100% !important;
        box-sizing: border-box !important;
      }}
      .pair-grid.mobile-stack td.pair-gap {{
        display: none !important;
      }}
      .pair-grid.mobile-stack td.pair-col.first {{
        margin-bottom: 10px;
      }}
      .pair-panel-inner,
      .card-inner,
      .pair-body {{ padding: 14px !important; }}
      .pair-head {{ padding: 10px 14px !important; }}
      .time-table th,
      .time-table td {{ padding: 10px 10px !important; font-size: 13px; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#FDF9F1;color:#3E3836;font-size:15px;line-height:1.7;font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC',Arial,sans-serif;">
  <table role="presentation" class="page" width="100%" style="width:100%;background:#FDF9F1;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" class="container" width="100%">
          <tr>
            <td>
              <table role="presentation" class="hero" width="100%" style="background:#FDF9F1;background-image:linear-gradient(135deg,#FDF9F1 0%,#F7EFE2 56%,#F3EADF 100%);border:1px solid #EADFCE;border-radius:22px;overflow:hidden;color:#3E3836;box-shadow:0 12px 30px rgba(110,84,58,0.10);">
                <tr>
                  <td class="hero-inner" style="padding:24px;background-color:rgba(255,255,255,0.24);">
                    <div class="hero-main" style="margin:0;font-size:24px;line-height:1.25;font-weight:600;color:#3E3836;font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC',Arial,sans-serif;text-shadow:0 1px 0 rgba(255,255,255,0.42);">{html.escape(result.solar_date)} {html.escape(result.weekday)}</div>
                    <div class="hero-sub" style="margin:6px 0 0;font-size:28px;line-height:1.3;font-weight:700;letter-spacing:0.02em;color:#9B3D3D;font-family:'Songti SC','STSong','SimSun','Noto Serif CJK SC','Noto Serif SC',serif;text-shadow:0 1px 0 rgba(255,255,255,0.42);">{html.escape(result.lunar_date)}</div>
                    <div class="meta-lines">
                      <div class="meta-line" style="margin-top:4px;font-size:16px;font-weight:500;line-height:1.45;color:#7A6C66;font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC',Arial,sans-serif;">干支：{html.escape(result.ganzhi)}</div>
                      <div class="meta-line" style="margin-top:4px;font-size:16px;font-weight:500;line-height:1.45;color:#7A6C66;font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC',Arial,sans-serif;">冲煞：{html.escape(result.zodiac_clash)}</div>
                      <div class="meta-line" style="margin-top:4px;font-size:16px;font-weight:500;line-height:1.45;color:#7A6C66;font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC',Arial,sans-serif;">建除十二神：{html.escape(result.officer12)}</div>
                      <div class="meta-line" style="margin-top:4px;font-size:16px;font-weight:500;line-height:1.45;color:#7A6C66;font-family:'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC',Arial,sans-serif;">吉凶等级：{html.escape(result.level_name)}</div>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr><td class="spacer">&nbsp;</td></tr>

          <tr>
            <td>
              <table role="presentation" class="pair-grid mobile-stack" width="100%">
                <tr>
                  <td class="pair-col first">
                    <div class="pair-panel-inner"><div class="label">节气</div><div class="value">{term_value}</div></div>
                  </td>
                  <td class="pair-gap">&nbsp;</td>
                  <td class="pair-col last">
                    <div class="pair-panel-inner"><div class="label">节日</div><div class="value">{holiday_value}</div></div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr><td class="spacer">&nbsp;</td></tr>

          <tr>
            <td>
              <table role="presentation" class="pair-card" width="100%">
                <tr><td class="pair-head good">宜</td></tr>
                <tr><td class="pair-body"><div class="tags">{render_badges(result.good_things, 'good')}</div></td></tr>
              </table>
            </td>
          </tr>

          <tr><td class="spacer">&nbsp;</td></tr>

          <tr>
            <td>
              <table role="presentation" class="pair-card" width="100%">
                <tr><td class="pair-head bad">忌</td></tr>
                <tr><td class="pair-body"><div class="tags">{render_badges(result.bad_things, 'bad')}</div></td></tr>
              </table>
            </td>
          </tr>

          <tr><td class="spacer">&nbsp;</td></tr>

          <tr>
            <td>
              <table role="presentation" class="pair-grid mobile-stack" width="100%">
                <tr>
                  <td class="first" style="vertical-align:top;">
                    <table role="presentation" class="pair-panel" width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr><td class="pair-head info">吉神</td></tr>
                      <tr><td class="pair-body"><div class="tags">{render_badges(result.good_gods, 'info')}</div></td></tr>
                    </table>
                  </td>
                  <td class="pair-gap">&nbsp;</td>
                  <td class="last" style="vertical-align:top;">
                    <table role="presentation" class="pair-panel" width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr><td class="pair-head warn">凶煞</td></tr>
                      <tr><td class="pair-body"><div class="tags">{render_badges(result.bad_gods, 'warn')}</div></td></tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr><td class="spacer">&nbsp;</td></tr>

          <tr>
            <td>
              <div class="section-title">时辰吉凶</div>
              <table role="presentation" class="time-table" width="100%">
                <thead>
                  <tr>
                    <th>时段</th>
                    <th>时辰</th>
                    <th>吉凶</th>
                  </tr>
                </thead>
                <tbody>
                  {hour_rows}
                </tbody>
              </table>
            </td>
          </tr>

          <tr>
            <td class="footer">Generated with cnlunar · Timezone: {TIMEZONE_NAME}</td>
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
    parser.add_argument("--save-dir", default="dist", help="输出目录，默认 dist")
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
