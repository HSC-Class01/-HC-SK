#!/usr/bin/env python3
"""Collect SK Inc. consolidated financial statements from OpenDART."""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "financial_data.json"
FILINGS_DIR = ROOT / "data" / "filings"
BASE = "https://opendart.fss.or.kr/api"
STOCK_CODE = "034730"
REPORTS = {"annual": "11011", "half_year": "11012", "Q1": "11013", "Q3": "11014"}
TIMEOUT = 45
MAX_FILING_BYTES = 15 * 1024 * 1024


def api_get(endpoint: str, **params) -> requests.Response:
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DART_API_KEY is missing. Add it to GitHub Actions repository secrets.")
    response = requests.get(f"{BASE}/{endpoint}", params={"crtfc_key": key, **params}, timeout=TIMEOUT)
    response.raise_for_status()
    return response


def api_json(endpoint: str, **params) -> dict:
    payload = api_get(endpoint, **params).json()
    if payload.get("status") != "000":
        raise RuntimeError(f"OpenDART {endpoint}: {payload.get('status')} {payload.get('message')}")
    return payload


def get_corp_code() -> str:
    payload = api_get("corpCode.xml")
    with zipfile.ZipFile(io.BytesIO(payload.content)) as archive:
        xml = archive.read("CORPCODE.xml").decode("utf-8", errors="replace")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    for item in root.findall("list"):
        if (item.findtext("stock_code") or "").strip() == STOCK_CODE:
            return (item.findtext("corp_code") or "").strip()
    raise RuntimeError(f"Could not find DART corp_code for stock code {STOCK_CODE}")


def number(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.strip().replace(",", "").replace("원", "")
    if cleaned in ("", "-", "N/A"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def row_value(rows: list[dict], keys: tuple[str, ...], names: tuple[str, ...], period_field: str) -> float | None:
    for row in rows:
        account_id = (row.get("account_id") or "").lower()
        if any(key.lower() == account_id for key in keys):
            value = number(row.get(period_field))
            if value is not None:
                return value
    for row in rows:
        name = (row.get("account_nm") or "").replace(" ", "")
        if any(target.replace(" ", "") in name for target in names):
            value = number(row.get(period_field))
            if value is not None:
                return value
    return None


def accounts(corp_code: str, year: int, report_code: str) -> list[dict]:
    payload = api_json("fnlttSinglAcntAll.json", corp_code=corp_code, bsns_year=year,
                       reprt_code=report_code, fs_div="CFS")
    return payload.get("list", [])


def extract(rows: list[dict], kind: str, previous_assets: float | None, previous_equity: float | None) -> dict:
    # DART supplies quarter-only values separately when available. Balance sheet uses period-end values.
    # On Q3 filings thstrm_amount is the standalone three-month figure while
    # thstrm_add_amount is the nine-month cumulative figure. Q1 has only the
    # first quarter in either field; half-year and annual statements are cumulative periods.
    income_field = "thstrm_amount" if kind == "Q3" else ("thstrm_add_amount" if kind == "Q1" else "thstrm_amount")
    sales = row_value(rows, ("ifrs-full_Revenue", "ifrs_Revenue"), ("매출액", "수익(매출액)", "영업수익"), income_field)
    operating = row_value(rows, ("ifrs-full_ProfitLossFromOperatingActivities",), ("영업이익", "영업손실"), income_field)
    net = row_value(rows, ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss"), ("당기순이익", "분기순이익", "반기순이익"), income_field)
    assets = row_value(rows, ("ifrs-full_Assets", "ifrs_Assets"), ("자산총계",), "thstrm_amount")
    liabilities = row_value(rows, ("ifrs-full_Liabilities", "ifrs_Liabilities"), ("부채총계",), "thstrm_amount")
    equity = row_value(rows, ("ifrs-full_Equity", "ifrs_Equity"), ("자본총계",), "thstrm_amount")
    current_assets = row_value(rows, ("ifrs-full_CurrentAssets",), ("유동자산",), "thstrm_amount")
    current_liabilities = row_value(rows, ("ifrs-full_CurrentLiabilities",), ("유동부채",), "thstrm_amount")
    def ratio(a, b, multiplier=100):
        return round(a / b * multiplier, 2) if a is not None and b not in (None, 0) else None
    avg_assets = (assets + previous_assets) / 2 if assets is not None and previous_assets else assets
    avg_equity = (equity + previous_equity) / 2 if equity is not None and previous_equity else equity
    return {
        "revenue": sales, "operating_income": operating, "net_income": net,
        "total_assets": assets, "total_liabilities": liabilities, "total_equity": equity,
        "current_assets": current_assets, "current_liabilities": current_liabilities,
        "ratios": {
            "debt_ratio_pct": ratio(liabilities, equity),
            "equity_ratio_pct": ratio(equity, assets),
            "current_ratio_pct": ratio(current_assets, current_liabilities),
            "operating_margin_pct": ratio(operating, sales),
            "net_margin_pct": ratio(net, sales),
            "roa_pct": ratio(net, avg_assets),
            "roe_pct": ratio(net, avg_equity),
            "asset_turnover": ratio(sales, avg_assets, 1),
        },
    }


def filing_index(corp_code: str, years: list[int]) -> dict[tuple[int, str], dict]:
    found = {}
    for year in years:
        payload = api_json("list.json", corp_code=corp_code, bgn_de= f"{year}0101", end_de=f"{year}1231",
                           pblntf_ty="A", page_count=100)
        for filing in payload.get("list", []):
            title = filing.get("report_nm", "")
            period_match = re.search(r"(20\d{2})\s*[.년/-]\s*(\d{1,2})", title)
            month = int(period_match.group(2)) if period_match else None
            code = None
            if "사업보고서" in title:
                code = "11011"
            elif "반기보고서" in title:
                code = "11012"
            elif "분기보고서" in title and (month == 9 or "3분기" in title):
                code = "11014"
            elif "분기보고서" in title and (month == 3 or "1분기" in title):
                code = "11013"
            if code:
                business_year = int(period_match.group(1)) if period_match else year
                if not period_match and code == "11011":
                    business_year -= 1
                key = (business_year, code)
                if key not in found or filing.get("rcept_no", "") > found[key].get("rcept_no", ""):
                    found[key] = filing
    return found


def save_latest_annual(filing: dict | None) -> dict | None:
    if not filing:
        return None
    rcept_no = filing["rcept_no"]
    info = {"report_nm": filing.get("report_nm"), "rcept_no": rcept_no,
            "rcept_dt": filing.get("rcept_dt"), "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"}
    try:
        response = api_get("document.xml", rcept_no=rcept_no)
        if len(response.content) <= MAX_FILING_BYTES:
            FILINGS_DIR.mkdir(parents=True, exist_ok=True)
            (FILINGS_DIR / f"SK_{rcept_no}.zip").write_bytes(response.content)
            info["local_file"] = f"data/filings/SK_{rcept_no}.zip"
        else:
            info["local_file"] = None
            info["download_note"] = "원문 ZIP이 15 MiB를 초과하여 DART 링크만 기록했습니다."
    except Exception as exc:  # Filing archives can be unavailable while normalized accounts remain usable.
        info["download_note"] = f"원문 내려받기 실패: {exc}"
    return info


def main() -> None:
    corp_code = get_corp_code()
    current_year = datetime.now(timezone.utc).year
    years = list(range(current_year - 6, current_year + 1))
    filings = filing_index(corp_code, years)
    periods = {"annual": [], "half_year": [], "quarterly": []}
    errors = []
    # Process periods in fiscal order so average-balance ratios can use the adjacent balance sheet.
    requests_to_make = []
    for year in years:
        for category, code in (("quarterly", "11013"), ("half_year", "11012"), ("quarterly", "11014"), ("annual", "11011")):
            if (year, code) in filings:
                requests_to_make.append((year, code, category, filings[(year, code)]))
    balances = {}
    for year, code, category, filing in requests_to_make:
        try:
            rows = accounts(corp_code, year, code)
            if not rows:
                continue
            label = {"11011": "연간", "11012": "반기", "11013": "1분기", "11014": "3분기"}[code]
            prior_key = (year - 1, "11011") if code in ("11011", "11013") else (year, "11013" if code == "11012" else "11012")
            prior = balances.get(prior_key, {})
            result = extract(rows, "Q1" if code == "11013" else ("Q3" if code == "11014" else label),
                             prior.get("assets"), prior.get("equity"))
            result.update({"year": year, "period": label, "report_code": code,
                           "receipt_no": filing.get("rcept_no"), "receipt_date": filing.get("rcept_dt"),
                           "report_name": filing.get("report_nm"),
                           "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={filing.get('rcept_no')}"})
            periods[category].append(result)
            balances[(year, code)] = {"assets": result.get("total_assets"), "equity": result.get("total_equity")}
            time.sleep(0.15)
        except Exception as exc:
            errors.append({"year": year, "report_code": code, "error": str(exc)})
    # Growth is year-over-year for matching annual, half-year, Q1, and Q3 periods.
    for category, entries in periods.items():
        by_key = {(x["year"], x["period"]): x for x in entries}
        for item in entries:
            prev = by_key.get((item["year"] - 1, item["period"]))
            item["ratios"]["revenue_growth_pct"] = None
            item["ratios"]["operating_income_growth_pct"] = None
            if prev:
                for value_key, growth_key in (("revenue", "revenue_growth_pct"), ("operating_income", "operating_income_growth_pct")):
                    a, b = item.get(value_key), prev.get(value_key)
                    item["ratios"][growth_key] = round((a - b) / b * 100, 2) if a is not None and b is not None and b > 0 else None
        entries.sort(key=lambda x: (x["year"], x["period"]))
    annual_filings = [filing for (year, code), filing in filings.items() if code == "11011"]
    latest_annual = max(annual_filings, key=lambda x: x.get("rcept_dt", ""), default=None)
    filing_meta = save_latest_annual(latest_annual)
    payload = {"company": {"name": "SK", "corp_code": corp_code, "stock_code": STOCK_CODE},
               "updated_at": datetime.now(timezone.utc).isoformat(), "source": "OpenDART",
               "currency_unit": "원", "statement_basis": "연결(CFS)", "periods": periods,
               "filings": [filing_meta] if filing_meta else [], "collection_errors": errors,
               "note": "재무 수치는 공시 기반이며 투자 권유가 아닙니다."}
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated {DATA}: corp_code={corp_code}; annual={len(periods['annual'])}; half={len(periods['half_year'])}; quarter={len(periods['quarterly'])}; errors={len(errors)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DART update failed: {exc}", file=sys.stderr)
        raise

