"""
The goal/point of this project is to extract Internship wage data by parsing pdfs.
To parse the pdfs, we imported the pdfplumber library: https://github.com/jsvine/pdfplumber
Numerous libraries like numpy, pandas, re were imported to handle input and output operations
"""

import os
import re
import pandas as pd
import pdfplumber

reports = "GraduationSurveyReports"
rows = []

# The following is a list of how we want our units to be ordered
unit_order = [
    "University-wide",
    "College of Agriculture and Natural Resources",
    "College of Arts and Humanities",
    "College of Behavioral and Social Sciences",
    "College of Computer, Mathematical, and Natural Sciences",
    "College of Education",
    "College of Information",
    "The A. James Clark School of Engineering",
    "Philip Merrill College of Journalism",
    "School of Architecture, Planning, and Preservation",
    "School of Public Health",
    "School of Public Policy",
    "The Robert H. Smith School of Business",
    "College Park Scholars",
    "Honors College",
    "Letters and Sciences",
    "Undergraduate Studies",
]

# Some PDFs use abbreviations in footers to indicate what section you’re in.
# This dictiotionary simply translates them over
ABBR_TO_UNIT = {
    "AGNR": "College of Agriculture and Natural Resources",
    "ARHU": "College of Arts and Humanities",
    "BSOS": "College of Behavioral and Social Sciences",
    "CMNS": "College of Computer, Mathematical, and Natural Sciences",
    "EDUC": "College of Education",
    "INFO": "College of Information",
    "ENGR": "The A. James Clark School of Engineering",
    "JOUR": "Philip Merrill College of Journalism",
    "ARCH": "School of Architecture, Planning, and Preservation",
    "SPHL": "School of Public Health",
    "PLCY": "School of Public Policy",
    "PPOL": "School of Public Policy",
    "BMGT": "The Robert H. Smith School of Business",
    "LTSC": "Letters and Sciences",
    "LESC": "Letters and Sciences",
    "HNRS": "Honors College",
    "CPS": "College Park Scholars",
    "UGST": "Undergraduate Studies",
    "UGS": "Undergraduate Studies",
    "OVERALL": "University-wide",
}
# Regex patterns that finds a match for footers 
FOOTER_ABBR_RE = re.compile(r"\b([A-Z]{3,8})\s+\d{1,3}\s*$")
FOOTER_TRAILNUM_RE = re.compile(r"^(?P<txt>.+?)\s+(?P<num>\d{1,3})\s*$")



# HELPER Functions :D

# cleans the data in order to make strings consistent from any whitespaces
def normalize_whitespace(s: str) -> str:
    s = (s or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

# Gets the year of the data
def infer_year_from_filename(fname: str):
    base = os.path.basename(fname) # Returns the file name

    # once a filename is returned we match using regex patterns
    m = re.match(r"^(20\d{2})", base)
    if m:
        return int(m.group(1))

    m = re.search(r"(20\d{2})\s*[-–]\s*(20\d{2})", base)
    if m:
        return int(m.group(2))

    years = re.findall(r"20\d{2}", base)
    return int(years[0]) if years else None

# Converts strings to ints
def to_int(s):
    s = str(s or "").replace(",", "").strip()
    return int(s) if s.isdigit() else None

# Converts strings to floats
def to_float(s):
    s = str(s or "").replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None

# Removes and fixes any fuzzy punctuation for consistency throughout the years
def unit_key(s: str) -> str:
    s = str(s or "").lower()
    s = s.replace("–", "-").replace("—", "-")
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = [t for t in s.split() if t != "and"]
    return " ".join(toks)

# Some years have typos so unit_lookup was created to catch all the typos
unit_lookup = {unit_key(u): u for u in unit_order}
unit_lookup[unit_key("Phillip Merrill College of Journalism")] = "Philip Merrill College of Journalism"
unit_lookup[unit_key("College of Information Studies")] = "College of Information"
unit_lookup[unit_key("Robert H. Smith School of Business")] = "The Robert H. Smith School of Business"
unit_lookup[unit_key("Robert H Smith School of Business")] = "The Robert H. Smith School of Business"
unit_lookup[unit_key("Office of Undergraduate Studies")] = "Undergraduate Studies"
unit_lookup[unit_key("Division of Undergraduate Studies")] = "Undergraduate Studies"

# Normalizes all units and find matches 
# whilst also looking for different variations for university wide
def canonicalize_unit(u: str) -> str:
    u = normalize_whitespace(u).replace("–", "-").replace("—", "-")
    low = u.lower().strip()

    if re.search(r"university\s*[- ]\s*wide|universitywide", low):
        return "University-wide"
    if low == "university of maryland":
        return "University-wide"
    if "university of maryland" in low and "overall" in low:
        return "University-wide"

    return unit_lookup.get(unit_key(u), u)

# Scan first ~60 lines for a unit name (handles wrapped titles)
def extract_unit_candidate(page_text: str):
    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    max_scan = min(60, len(lines))

    def test(s: str):
        cand = canonicalize_unit(s.replace(" ,", ","))
        return cand if cand in unit_order else None

    for i in range(max_scan):
        hit = test(lines[i])
        if hit:
            return hit

        if i + 1 < max_scan:
            two = (lines[i].rstrip(",") + " " + lines[i + 1]).strip()
            hit = test(two)
            if hit:
                return hit

        if i + 2 < max_scan:
            three = (lines[i].rstrip(",") + " " + lines[i + 1] + " " + lines[i + 2]).strip()
            hit = test(three)
            if hit:
                return hit

    return None

# This function checks only the bottom of the page for footers.
def extract_unit_from_footer(page_text: str):

    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    for ln in reversed(lines[-12:]):
        m = FOOTER_ABBR_RE.search(ln)
        if m:
            code = m.group(1)
            if code in ABBR_TO_UNIT:
                return ABBR_TO_UNIT[code]

        m2 = FOOTER_TRAILNUM_RE.match(ln)
        if m2:
            cand = canonicalize_unit(m2.group("txt"))
            if cand in unit_order:
                return cand

        if re.search(r"\boverall\b", ln, flags=re.I):
            return "University-wide"

    return None

# A fall back method that checks if units are mentioned anywhere on the page
def extract_unit_anywhere(page_text: str):
    """Last-resort: if a page contains the literal unit name anywhere."""
    low = (page_text or "").lower()
    hits = [u for u in unit_order if u.lower() in low]
    return max(hits, key=len) if hits else None


def page_starts_with_unit(page_text: str):

    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]
    if not lines:
        return None

    # try first 1–3 lines (handles wrapped unit titles)
    for span in (1, 2, 3):
        if len(lines) >= span:
            cand = canonicalize_unit(" ".join(lines[:span]))
            if cand in unit_order:
                return cand
    return None

# Look ahead ONLY for pages that actually START a unit section (top lines),
# not pages that merely mention units in an index/table.
def lookahead_unit_start(pdf, page_index: int, max_ahead: int = 1):

    for j in range(1, max_ahead + 1):
        k = page_index + j
        if k >= len(pdf.pages):
            break
        nxt = pdf.pages[k].extract_text() or ""
        u = page_starts_with_unit(nxt)
        if u:
            return u
    return None



# Strip pie chart data using regex
def strip_chart_artifacts(text: str) -> str:
    t = normalize_whitespace(text)
    t = re.sub(r"internships?\s*-\s*compensation", " ", t, flags=re.I)
    t = re.sub(r"\b(?:yes|no|other|paid|unpaid)\b\s*\d+(?:\.\d+)?\s*%?", " ", t, flags=re.I)
    t = re.sub(r"\d+(?:\.\d+)?\s*%", " ", t)
    t = re.sub(r"\b(?:yes|no|other)\b", " ", t, flags=re.I)
    return normalize_whitespace(t)



# Finally we have the parsers that look for the patterns like hourly wage
# or paid/unpaid to get wage metrics
SENT_GAP = r"(?:(?![.?!]).){0,260}?"

WAGE_PATTERNS = [
    re.compile(
        rf"\b(?:of|for)\s+(?:the\s+)?(?P<n>[\d,]+)\s+(?:internship\s+)?experiences\b"
        rf"{SENT_GAP}\b(?:that\s+)?(?:paid|include(?:d)?|with)\b"
        rf"{SENT_GAP}\bhourly\b{SENT_GAP}\b(?:wage|rate)\b"
        rf"{SENT_GAP}(?:average|mean)\b.*?\$?\s*(?P<avg>\d+(?:\.\d+)?)(?!\s*%)"
        rf"{SENT_GAP}\bmedian\b.*?\$?\s*(?P<med>\d+(?:\.\d+)?)(?!\s*%)",
        re.I,
    ),
    re.compile(
        rf"\b(?:of|for)\s+(?:the\s+)?(?P<n>[\d,]+)\s+(?:internship\s+)?experiences\b"
        rf"{SENT_GAP}\b(?:that\s+)?(?:paid|include(?:d)?|with)\b"
        rf"{SENT_GAP}\bhourly\b{SENT_GAP}\b(?:wage|rate)\b"
        rf"{SENT_GAP}\bmedian\b.*?\$?\s*(?P<med>\d+(?:\.\d+)?)(?!\s*%)"
        rf"{SENT_GAP}(?:average|mean)\b.*?\$?\s*(?P<avg>\d+(?:\.\d+)?)(?!\s*%)",
        re.I,
    ),
]

ONE_WAGE_RE = re.compile(
    r"\b(?:one|1)\s+experience\b.*?\bpaid\b.*?\bhourly\b.*?\b(?:wage|rate)\b.*?"
    r"\$?\s*(?P<w>\d+(?:\.\d+)?)\b.*?\bper\s+hour\b",
    re.I,
)

TOTAL_EXPERIENCES_RE = re.compile(
    r"\b(?:a\s+)?total\s+of\s+(?P<t>[\d,]+)\s+internship\s+experience(?:s)?\s+(?:were|was)\s+reported\b",
    re.I,
)

def parse_metrics(page_text: str):
    cleaned = strip_chart_artifacts(page_text)
    low = cleaned.lower()

    # Wage metrics first
    if ("hourly" in low) and (("wage" in low) or ("rate" in low)) and ("median" in low) and (("average" in low) or ("mean" in low)):
        for pat in WAGE_PATTERNS:
            m = pat.search(cleaned)
            if not m:
                continue
            n = to_int(m.group("n"))
            avg = to_float(m.group("avg"))
            med = to_float(m.group("med"))
            if n is None or avg is None or med is None:
                continue
            if not (0 < avg < 100 and 0 < med < 100):
                continue
            return {"n": n, "avg": avg, "med": med, "priority": 2}

        m = ONE_WAGE_RE.search(cleaned)
        if m:
            w = to_float(m.group("w"))
            if w is not None and 0 < w < 100:
                return {"n": 1, "avg": w, "med": w, "priority": 2}

    # Total-only fallback
    if "internship" in low and "total" in low and "reported" in low:
        m = TOTAL_EXPERIENCES_RE.search(cleaned)
        if m:
            t = to_int(m.group("t"))
            if t is not None and t > 0:
                return {"n": t, "avg": None, "med": None, "priority": 1}

    return None


"""
This is the main block of code that runs the script 
that splits and scans PDFs, pages, tables
"""
pdf_files = sorted([f for f in os.listdir(reports) if f.lower().endswith(".pdf")])

years_in_folder = sorted({
    infer_year_from_filename(f)
    for f in pdf_files
    if infer_year_from_filename(f) is not None
})


for file in pdf_files:
    year = infer_year_from_filename(file)
    if year is None:
        continue

    pdf_path = os.path.join(reports, file)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            current_unit = None

            for page_index, page in enumerate(pdf.pages):
                try:
                    raw = page.extract_text() or ""
                except Exception:
                    continue

                if not raw.strip():
                    continue

                # Detect unit on this page (best -> worst)
                page_unit = (
                    extract_unit_candidate(raw)
                    or extract_unit_from_footer(raw)
                    or extract_unit_anywhere(raw)
                )

                if page_unit:
                    current_unit = page_unit

                metrics = parse_metrics(raw)
                if not metrics:
                    continue

                # Only lookahead if the NEXT page *starts* a unit section.
                if page_unit:
                    unit = page_unit
                else:
                    la = lookahead_unit_start(pdf, page_index, max_ahead=1)
                    if la:
                        unit = la
                        current_unit = la
                    else:
                        unit = current_unit or "University-wide"

                unit = canonicalize_unit(unit)

                rows.append({
                    "Year": year,
                    "Unit": unit,
                    "Internship Wage N": metrics["n"],
                    "Internship Wage Average": (round(metrics["avg"], 2) if metrics["avg"] is not None else None),
                    "Internship Wage Median": (round(metrics["med"], 2) if metrics["med"] is not None else None),
                    "pdf": file,
                    "page": page_index + 1,
                    "priority": metrics["priority"],
                })

    except Exception:
        continue

# Build df
df = pd.DataFrame(
    rows,
    columns=[
        "Year", "Unit",
        "Internship Wage N", "Internship Wage Average", "Internship Wage Median",
        "pdf", "page", "priority",
    ],
)

# Deduplicate per (Year, Unit): prefer wage metrics (priority=2), then earliest page
if not df.empty:
    df = (
        df.sort_values(["Year", "Unit", "priority", "page"], ascending=[True, True, False, True])
          .drop_duplicates(["Year", "Unit"], keep="first")
          .reset_index(drop=True)
    )

# Full Year x Unit grid
full_index = pd.MultiIndex.from_product([years_in_folder, unit_order], names=["Year", "Unit"])
out = (
    df.set_index(["Year", "Unit"])
      .reindex(full_index)
      .reset_index()
)

# Using pandas to format our CSV the way want to
out["Year"] = out["Year"].astype("Int64")
out["Internship Wage N"] = pd.to_numeric(out["Internship Wage N"], errors="coerce").astype("Int64")
out["Internship Wage Average"] = pd.to_numeric(out["Internship Wage Average"], errors="coerce")
out["Internship Wage Median"] = pd.to_numeric(out["Internship Wage Median"], errors="coerce")

# Final columns/order
out = out[["Unit", "Year", "Internship Wage N", "Internship Wage Average", "Internship Wage Median"]]
out["Unit_cat"] = pd.Categorical(out["Unit"], categories=unit_order, ordered=True)
out = (
    out.sort_values(["Year", "Unit_cat"], ascending=[True, True])
       .drop(columns=["Unit_cat"])
       .reset_index(drop=True)
)

out.to_csv("internship_salary_week3.csv", index=False, na_rep="")
