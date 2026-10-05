"""
Reads ONLY the navadna malica (NV column) for the whole week from the
official gimvic.org jedilnik PDF and saves it to menu.json.

Setup:  pip install requests beautifulsoup4 pdfplumber
Run:    python fetch_menu.py      (the GitHub workflow runs it every Monday)
"""
import io, json, re
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

PAGE = "https://www.gimvic.org/delovanjesole/solske_sluzbe_in_solski_organi/solska_prehrana/"
HEADERS = {"User-Agent": "malica-fetcher/1.0 (personal project)"}
DAY = re.compile(r"^(PONEDELJEK|TOREK|SREDA|ČETRTEK|PETEK)$")
DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")


def find_pdf():
    r = requests.get(PAGE, headers=HEADERS, timeout=20)
    r.raise_for_status()
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        if "malica" in a.get_text().lower() and ".pdf" in a["href"]:
            return urljoin(PAGE, a["href"]), a.get_text(" ", strip=True)
    raise SystemExit("Could not find the MALICA link - has the page changed?")


def parse(pdf):
    days, cur = [], None
    for page in pdf.pages:
        words = page.extract_words()
        vpr = next((w for w in words if w["text"] == "Vpr"), None)
        edge = vpr["x0"] - 2 if vpr else page.width / 4  # right edge of NV column
        lines = []
        for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
            if lines and abs(lines[-1][0] - w["top"]) < 3:
                lines[-1][1].append(w)
            else:
                lines.append([w["top"], [w]])
        for _, ws in lines:
            left = [w["text"] for w in sorted(ws, key=lambda w: w["x0"]) if w["x0"] < edge]
            if not left:
                continue
            text = " ".join(left)
            if text.startswith(("NV in", "*", "Alergeni", "med odmori")):
                continue
            if DAY.match(left[0]):
                cur = {"n": left[0].capitalize(), "d": None, "items": []}
                days.append(cur)
                left = left[1:]
                text = " ".join(left)
            if cur is None:
                continue
            if left and DATE.match(left[0]):
                dd, mm, yy = DATE.match(left[0]).groups()
                cur["d"] = f"{yy}-{int(mm):02d}-{int(dd):02d}"
                rest = " ".join(left[1:])          # e.g. "(NV 2kos)"
                if rest and cur["items"]:
                    cur["items"][-1] += " " + rest
                continue
            if text:
                cur["items"].append(text)
    return days


url, title = find_pdf()
pdf_bytes = requests.get(url, headers=HEADERS, timeout=30).content
with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
    days = parse(pdf)

if len(days) < 5:
    raise SystemExit(f"Expected 5 days, got {len(days)} - check the PDF layout.")

json.dump({"week": title, "source": url, "days": days},
          open("menu.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("Saved menu.json:", title)
