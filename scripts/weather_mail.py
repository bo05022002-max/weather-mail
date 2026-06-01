"""
기상청 단기예보 API → Gmail 자동 발송
남양주 진접읍 (NX=64, NY=130)
"""

import os
import math
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── 환경변수 ──────────────────────────────────────────
KMA_API_KEY = os.environ["KMA_API_KEY"]
GMAIL_USER  = os.environ["GMAIL_USER"]
GMAIL_APP_PW = os.environ["GMAIL_APP_PW"]
MAIL_TO     = os.environ["MAIL_TO"]

# ── 기상청 API 설정 ───────────────────────────────────
BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
NX, NY = 64, 130

ANNOUNCE_HOURS = [2, 5, 8, 11, 14, 17, 20, 23]

def get_base_time(now_kst: datetime) -> tuple[str, str]:
    for h in reversed(ANNOUNCE_HOURS):
        if now_kst.hour >= h + 1:
            base_dt = now_kst.replace(hour=h, minute=0, second=0, microsecond=0)
            return base_dt.strftime("%Y%m%d"), f"{h:02d}00"
    prev = now_kst - timedelta(days=1)
    return prev.strftime("%Y%m%d"), "2300"

def fetch_forecast(base_date: str, base_time: str) -> list[dict]:
    params = {
        "serviceKey": KMA_API_KEY,
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": NX,
        "ny": NY,
    }
    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    items = resp.json()["response"]["body"]["items"]["item"]
    return items

def wind_chill(T: float, V: float) -> float:
    if V <= 0:
        return T
    return 13.12 + 0.6215 * T - 11.37 * (V ** 0.16) + 0.3965 * (V ** 0.16) * T

def parse_items(items: list[dict], target_date: str) -> list[dict]:
    data: dict[str, dict] = {}
    for item in items:
        if item["fcstDate"] != target_date:
            continue
        t = item["fcstTime"]
        cat = item["category"]
        val = item["fcstValue"]
        data.setdefault(t, {})[cat] = val

    rows = []
    for t in sorted(data.keys()):
        d = data[t]
        try:
            tmp = float(d.get("TMP", "NaN"))
            wsd = float(d.get("WSD", 0))
            reh = d.get("REH", "-")
            wci = wind_chill(tmp, wsd)
            rows.append({
                "time": f"{int(t[:2])}시",
                "wci":  f"{wci:.0f}°C",
                "tmp":  f"{tmp:.0f}°C",
                "reh":  f"{reh}%",
            })
        except (ValueError, TypeError):
            continue
    return rows

def build_table(rows: list[dict]) -> str:
    lines = [
        "┌──────┬────────┬────────┬──────┐",
        "│ 시간 │ 체감온도│  기온  │  습도 │",
        "├──────┼────────┼────────┼──────┤",
    ]
    for r in rows:
        lines.append(
            f"│ {r['time']:^4} │ {r['wci']:^6} │ {r['tmp']:^6} │ {r['reh']:^4} │"
        )
    lines.append("└──────┴────────┴────────┴──────┘")
    return "\n".join(lines)

def send_mail(subject: str, body: str):
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_USER
    msg["To"]      = MAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.ehlo()
        s.starttls()
        s.login(GMAIL_USER, GMAIL_APP_PW)
        s.sendmail(GMAIL_USER, MAIL_TO, msg.as_string())

def main():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    base_date, base_time = get_base_time(now_kst)
    target_date = now_kst.strftime("%Y%m%d")

    items = fetch_forecast(base_date, base_time)
    rows  = parse_items(items, target_date)

    if not rows:
        print("예보 데이터 없음")
        return

    table = build_table(rows)
    announce_hour = int(base_time[:2])
    subject = (
        f"[날씨] 진접읍 {now_kst.strftime('%Y-%m-%d')} "
        f"{announce_hour}시 기준"
    )
    body = f"{subject}\n\n{table}\n"

    send_mail(subject, body)
    print(f"메일 발송 완료: {subject}")

if __name__ == "__main__":
    main()
