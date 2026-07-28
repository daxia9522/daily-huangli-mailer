#!/usr/bin/env python3
from __future__ import annotations

from main import build_result, parse_target_datetime, resolve_save_dir


def test_2026_07_28() -> None:
    r = build_result(parse_target_datetime("2026-07-28"))
    assert r.solar_date == "2026-07-28"
    assert r.weekday == "星期二"
    assert "六月" in r.lunar_date and "十五" in r.lunar_date
    assert r.ganzhi == "丙午年 乙未月 癸卯日"
    assert "冲鸡" in r.zodiac_clash and "煞西" in r.zodiac_clash
    assert r.officer12.startswith("成日")
    assert r.day_star == "天德"
    assert "黄道" in r.day_path
    assert "吉" in r.level_short
    assert r.good_things[:5] == ["嫁娶", "订盟", "纳采", "祭祀", "祈福"]
    assert r.bad_things == ["入宅", "开市", "掘井", "词讼", "合寿木"]
    assert "母仓" in r.good_gods
    assert r.bad_gods == ["大煞"]
    assert len(r.hour_luck) == 13
    assert r.hour_luck[0]["slot"] == "00:00-00:59"
    assert r.hour_luck[0]["ganzhi"] == "壬子"
    assert r.hour_luck[7]["luck"] == "吉"
    assert r.hour_luck[-1]["slot"] == "23:00-23:59"


def test_anchors() -> None:
    spring = build_result(parse_target_datetime("2026-02-17"))
    assert "春节" in spring.holidays
    term = build_result(parse_target_datetime("2026-07-23"))
    assert term.today_term_exact and term.current_term.name == "大暑"


def test_save_dir() -> None:
    assert resolve_save_dir("") is None
    assert resolve_save_dir("none") is None
    assert resolve_save_dir("dist") == "dist"


if __name__ == "__main__":
    test_2026_07_28()
    test_anchors()
    test_save_dir()
    print("ok")
