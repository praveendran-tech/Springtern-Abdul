"""
The goal/point of this script is to extract employment search data by parsing pdfs.
To parse the pdfs, we imported the pdfplumber library: https://github.com/jsvine/pdfplumber
Numerous libraries like numpy, pandas, re were imported to handle input and output operations
"""
import os
import re
import pandas as pd
import pdfplumber

reports = "GraduationSurveyReports"
rows = [] # This variable is used to just extract the table row data to later transform into a DataFrame

"""
The following regex patterns are used to define what a percent looks like in the data 
percent_re matches all numbers with percent sign like 90.0% or <1%
pct_anywhere checks if there is a percent somwhere inside a line
"""
percent_re = re.compile(r"^<?\d+(?:\.\d+)?%$")
pct_anywhere = re.compile(r"(<?\d+(?:\.\d+)?)\s*%")

# A filter for words that are common and aren't real labels
HEADER_WORDS = {"method", "methods", "used", "find", "employment", "search"}

# Markers to tell the script when to stop parsing
STOP_MARKERS = (
    "reported outcomes",
    "graduate outcomes",
    "placement rate",
    "employed ft",
    "employed pt",
    "continuing education",
    "volunteering",
    "service program",
    "serving in the military",
    "starting a business",
    "unplaced",
    "unresolved",
    "salary",
)
# HELPER FUNCTIONS ;)

# Function to convert input to a string and remove any and all whitespaces
def clean(x):
    if x is None:
        return ""
    return str(x).replace("\n", " ").strip()

# Remove spaces and detects if input is a percentage
def is_percent(x):
    return bool(percent_re.match(clean(x).replace(" ", "")))

# Checks if line contains ONLY a percent
def is_percent_only_line(ln: str) -> bool:
    return is_percent(ln)

# Used to map data that have multiple candidates so it standardizes to the largest one
def pct_to_num(pct: str) -> float:
    pct = (pct or "").strip()
    if not pct:
        return -1.0
    if pct.startswith("<") and pct.endswith("%"):
        return 0.5
    try:
        return float(pct.rstrip("%"))
    except ValueError:
        return -1.0

# Checks whether or not input is a valid label
def is_label(s):
    s = clean(s)
    if not s:
        return False
    if is_percent(s):
        return False
    if s.replace(",", "").isdigit():
        return False

    low = s.lower()
    words = re.findall(r"[a-z]+", low)
    if not words:
        return False

    if all(w in HEADER_WORDS for w in words):
        return False

    return any(ch.isalpha() for ch in s)

# The officiial list of units
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

# clean unit strings + detect University-wide
def normalize_unit(u: str) -> str:
    u = str(u or "").strip()
    u = re.sub(r"\s+", " ", u)
    u = u.replace("–", "-").replace("—", "-")

    low = u.lower()

    if "university of maryland" in low and "overall" in low:
        return "University-wide"
    if re.search(r"university\s*[- ]\s*wide|universitywide", low):
        return "University-wide"
    if low == "university of maryland":
        return "University-wide"

    return u

# build a “matching key” for unit strings
def unit_key(s: str) -> str:
    s = str(s or "").lower()
    s = s.replace("–", "-").replace("—", "-")
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = [t for t in s.split() if t != "and"]
    return " ".join(toks)

unit_lookup = {unit_key(u): u for u in unit_order}
unit_lookup[unit_key("Phillip Merrill College of Journalism")] = "Philip Merrill College of Journalism"
unit_lookup[unit_key("Philip Merrill College of Journalism")] = "Philip Merrill College of Journalism"
unit_lookup[unit_key("Robert H. Smith School of Business")] = "The Robert H. Smith School of Business"
unit_lookup[unit_key("Robert H Smith School of Business")] = "The Robert H. Smith School of Business"
unit_lookup[unit_key("Office of Undergraduate Studies")] = "Undergraduate Studies"
unit_lookup[unit_key("Division of Undergraduate Studies")] = "Undergraduate Studies"
unit_lookup[unit_key("College of Information Studies")] = "College of Information"

def canonicalize_unit(u: str) -> str:
    u = normalize_unit(u)
    k = unit_key(u)
    if k in unit_lookup:
        return unit_lookup[k]
    return u

# Extracts the first 60 lines to look for units
def extract_unit_candidate(page_text: str):
    lines = [ln.strip() for ln in (page_text or "").split("\n") if ln.strip()]
    max_scan = min(60, len(lines))

    def test_candidate(s: str):
        s = s.replace(" ,", ",")
        cand = canonicalize_unit(s)
        return cand if cand in unit_order else None

    for i in range(max_scan):
        hit = test_candidate(lines[i])
        if hit:
            return hit

        if i + 1 < max_scan:
            two = (lines[i].rstrip(",") + " " + lines[i + 1]).strip()
            hit = test_candidate(two)
            if hit:
                return hit

        if i + 2 < max_scan:
            three = (lines[i].rstrip(",") + " " + lines[i + 1] + " " + lines[i + 2]).strip()
            hit = test_candidate(three)
            if hit:
                return hit

    return None

# Standardize method labels
def method_key(s: str):
    s = (s or "").lower()
    s = re.sub(r"\s+", " ", s).strip()

    if "intern" in s or "co-op" in s or "coop" in s:
        return "Previous Internship/Co-op %"

    if "career fair" in s or "career fairs" in s:
        if "non-umd" in s or "non umd" in s or "off campus" in s or "off-campus" in s:
            return "Career Fairs Off Campus %"
        if "umd" in s:
            return "Career Fairs On Campus %"
        return "Career Fairs On Campus %"

    if "non-umd" in s or "non umd" in s:
        if ("online" in s) or ("job site" in s) or ("jobsite" in s) or ("company website" in s) or ("company site" in s) or ("social media" in s):
            return "Non-UMD Online Job Site %"

    if ("umd online job site" in s) or ("handshake" in s) or ("hiresmith" in s) or ("careers4terps" in s):
        if "non-umd" not in s and "non umd" not in s:
            return "UMD Online Job Site %"

    if "interview" in s:
        if ("on campus" in s) or ("on-campus" in s) or ("campus/virtual" in s) or ("virtual" in s):
            return "On-campus Interviews %"

    if ("family" in s or "friends" in s) and ("contact" in s or "contacts" in s):
        return "Contacts Family/Friends %"
    if ("faculty" in s or "staff" in s) and ("contact" in s or "contacts" in s):
        return "Contacts Faculty %"

    if "currently employed" in s:
        return "Currently Employed with Org %"

    if "newspaper" in s:
        return "Newspaper %"
    if s.strip() == "other":
        return "Other %"

    return None

# Detect if a page contains the employment-search section
def page_has_employment_search(page_text: str):
    return bool(re.search(
        r"employment\s+search|method\s+used\s+to\s+find\s+employment|methods\s+of\s+employment",
        page_text or "",
        re.I
    ))

# Not all data is in table form, so this method extracts from the text itself
def parse_ep_from_text(page_text: str):
    page_low = (page_text or "").lower()

    idx_es = page_low.find("employment search")
    idx_tfr = page_low.find("too few responses")
    if idx_es != -1 and idx_tfr != -1 and idx_tfr > idx_es:
        return []

    lines = [ln.strip() for ln in (page_text or "").splitlines() if ln.strip()]

    start = None
    for i, ln in enumerate(lines):
        ln_low = ln.lower()
        if "employment search" in ln_low or "method used to find employment" in ln_low or "methods of employment" in ln_low:
            start = i
            break
    if start is None:
        return []

    out = []
    pending_label = None
    pending_pct = None

    for ln in lines[start + 1:]:
        line_low = ln.lower()

        if any(m in line_low for m in STOP_MARKERS):
            break

        if "based on" in line_low and "responses" in line_low:
            continue
        if "method used to find employment" in line_low or "methods of employment" in line_low:
            continue
        if "employment search" in line_low:
            continue

        if is_percent_only_line(ln):
            if pending_label and is_label(pending_label):
                out.append((pending_label, clean(ln)))
                pending_label = None
                pending_pct = None
            else:
                pending_pct = clean(ln)
            continue

        matches = list(pct_anywhere.finditer(ln))
        if matches:
            prev_end = 0
            for m in matches:
                pct = m.group(1).replace(" ", "") + "%"
                label = ln[prev_end:m.start()].strip(" -:\t")
                prev_end = m.end()

                if not label and pending_label:
                    label = pending_label

                if label and is_label(label) and is_percent(pct):
                    out.append((label, pct))

            pending_label = None
            pending_pct = None
            continue

        if is_label(ln):
            if pending_pct and is_percent(pending_pct):
                out.append((ln, pending_pct))
                pending_pct = None
                pending_label = None
            else:
                if pending_label and not pending_pct:
                    pending_label = (pending_label + " " + ln).strip()
                else:
                    pending_label = ln
            continue

    seen = set()
    dedup = []
    for label, pct in out:
        key = (label.lower(), pct)
        if key not in seen:
            seen.add(key)
            dedup.append((label, pct))

    return dedup

# Gets the year associated with the file
def infer_year_from_filename(fname: str):
    m = re.match(r"^(20\d{2})", fname)
    if m:
        return int(m.group(1))

    m = re.search(r"(20\d{2})\s*[-–]\s*(20\d{2})", fname)
    if m:
        return int(m.group(2))

    years = re.findall(r"20\d{2}", fname)
    return max(map(int, years)) if years else None

"""
This is the main block of code that runs the script 
that splits and scans PDFs, pages, tables
"""

for file in os.listdir(reports):
    if not file.endswith(".pdf"):
        continue

    pdf_path = os.path.join(reports, file)

    with pdfplumber.open(pdf_path) as pdf:
        current_unit = None

        for page in pdf.pages:
            page_text = page.extract_text() or ""

            unit_here = extract_unit_candidate(page_text)
            if unit_here and not page_has_employment_search(page_text):
                current_unit = unit_here

            if not current_unit:
                continue

            if not page_has_employment_search(page_text):
                continue

            parsed = parse_ep_from_text(page_text)

            best_for_method = {}

            for label, pct in parsed:
                mk = method_key(label)
                if not mk:
                    continue

                if (mk not in best_for_method) or (pct_to_num(pct) > pct_to_num(best_for_method[mk][1])):
                    best_for_method[mk] = (label, pct)

            for mk, (label, pct) in best_for_method.items():
                rows.append({
                    "pdf": file,
                    "Unit": current_unit,
                    "method": label,
                    "Method": mk,
                    "percent": pct,
                })

df = pd.DataFrame(rows)
print("Extracted rows:", len(df))

df["Year"] = df["pdf"].apply(infer_year_from_filename).astype("Int64")
df["Unit"] = df["Unit"].apply(canonicalize_unit)

method_columns = [
    "On-campus Interviews %",
    "Previous Internship/Co-op %",
    "Career Fairs On Campus %",
    "Career Fairs Off Campus %",
    "UMD Online Job Site %",
    "Non-UMD Online Job Site %",
    "Contacts Faculty %",
    "Contacts Family/Friends %",
    "Currently Employed with Org %",
    "Newspaper %",
    "Other %",
]

wide = (
    df.pivot_table(
        index=["Unit", "Year"],
        columns="Method",
        values="percent",
        aggfunc="first",
    )
    .reset_index()
)

for c in method_columns:
    if c not in wide.columns:
        wide[c] = pd.NA

wide = wide[["Unit", "Year"] + method_columns]

all_years = sorted(df["Year"].dropna().astype(int).unique())
full_index = pd.MultiIndex.from_product([unit_order, all_years], names=["Unit", "Year"])

wide = (
    wide.set_index(["Unit", "Year"])
        .reindex(full_index)
        .reset_index()
)

wide["Unit_cat"] = pd.Categorical(wide["Unit"], categories=unit_order, ordered=True)
wide = (
    wide.sort_values(["Year", "Unit_cat"], ascending=[True, True])
        .drop(columns=["Unit_cat"])
        .reset_index(drop=True)
)

wide.to_csv("employment_search_week2.csv", index=False)
