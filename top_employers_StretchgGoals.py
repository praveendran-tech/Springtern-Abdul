"""
The goal/point of this project is to extract top employer data by parsing pdfs.
To parse the pdfs, we imported the pdfplumber library: https://github.com/jsvine/pdfplumber
Numerous libraries like numpy, pandas, re were imported to handle input and output operations
"""

import os
import re
import pandas as pd
import pdfplumber

rows = []  # This variable stores the final output rows to later transform into a DataFrame
reports = "GraduationSurveyReports" 

#Column value we want in the output
UNIT_NAME = "University-wide"  

"""
The following regex patterns help us locate and parse the "Top Employers" section.

HEADING_RE matches the start of the Top Employers block.
STOP_RE detects when we've moved past the Top Employers block into another section.
COUNT_LINE_RE detects a typical employer row like: "Deloitte 63"
COUNT_ONLY_RE detects a line that is just a count (used when employer names wrap to the next line).
YEAR_RE extracts the year from the PDF filename.
"""
HEADING_RE = re.compile(r"\bTOP\s+EMPLOYERS\b", re.IGNORECASE)

STOP_RE = re.compile(
    r"(GEOGRAPHIC\s+DISTRIBUTION|TOP\s+10|CONTINUING\s+EDUCATION|OUT\s+OF\s+CLASSROOM|"
    r"STARTING\s+A\s+BUSINESS|SERVICE/VOLUNTEER|INTERNSHIP\s+PARTICIPATION)",
    re.IGNORECASE,
)

COUNT_LINE_RE = re.compile(r"^(?P<name>.+?)\s+(?P<count>\d[\d,]*)\s*$")
COUNT_ONLY_RE = re.compile(r"^\d[\d,]*\s*$")

YEAR_RE = re.compile(r"(20\d{2})")

# HELPER FUNCTIONS :)

# Cleans up a line by removing weird spacing and making it easier to match with regex
def normalize_line(ln: str) -> str:
    return re.sub(r"\s+", " ", (ln or "").replace("\u00a0", " ")).strip()

# Extracts the year (e.g. 2019) from a PDF filename using regex
def year_from_filename(filename: str):
    m = YEAR_RE.search(filename)
    return int(m.group(1)) if m else None

"""
This function is the main heart of the script.
It finds the Top Employers heading inside a PDF and returns ONLY the first employer listed
"""
def extract_top_employer(pdf_path: str, max_pages: int = 25):
    collecting = False  # Tracks whether we've found the Top Employers heading yet
    buffer = ""

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = min(max_pages, len(pdf.pages))

        for p in range(n_pages):
            text = pdf.pages[p].extract_text() or ""
            lines = [normalize_line(x) for x in text.splitlines()]

            for ln in lines:
                if not ln:
                    continue

                # Find the heading line "TOP EMPLOYERS ..."
                if not collecting:
                    # Avoid internship-related headings if they appear
                    if HEADING_RE.search(ln) and "INTERNSHIP" not in ln.upper() and "SAMPLE" not in ln.upper():
                        collecting = True
                        buffer = ""
                    continue

                # If we hit another major section before grabbing a top employer, stop
                if STOP_RE.search(ln):
                    return ""

                # Skip header-ish lines that aren't actual employer entries
                if HEADING_RE.search(ln) or ln.upper().startswith("REPORTED") or ln.upper().startswith("TOP EMPLOYERS"):
                    continue

                # Typical case: employer + count on the same line ("Deloitte 63")
                m = COUNT_LINE_RE.match(ln)
                if m:
                    name = normalize_line(m.group("name"))

                    # If part of the name was on previous line, combine it
                    if buffer:
                        name = normalize_line(buffer + " " + name)
                        buffer = ""
                    return name

                # Wrapped case: employer name stored in buffer, count appears on next line
                if buffer and COUNT_ONLY_RE.match(ln):
                    return buffer

                # If line contains letters, treat it as part of a wrapped employer name
                if re.search(r"[A-Za-z]", ln) and not STOP_RE.search(ln):
                    buffer = normalize_line((buffer + " " + ln).strip()) if buffer else ln

    return "" 


"""
This is the main block of code that runs the script.
It scans the folder of PDFs, extracts the year from each filename,
pulls the top employer for that year, and writes everything into a CSV.
"""

year_to_pdf = {}   # Maps years to pdf file path (so we can output one row per year)
years_found = set() 

for filename in os.listdir(reports):
    if not filename.lower().endswith(".pdf"):
        continue
    # Extract year from filename
    year = year_from_filename(filename)  
    if year is None:
        continue

    years_found.add(year)

    if year not in year_to_pdf:
        year_to_pdf[year] = os.path.join(reports, filename)

# For each year we found, extract the top employer and build output rows
for year in sorted(years_found):
    pdf_path = year_to_pdf.get(year)

    # If the PDF path is missing for some reason, output N/A
    if not pdf_path or not os.path.exists(pdf_path):
        rows.append({"Unit": UNIT_NAME, "Year": year, "Employer Names": "N/A"})
        continue

    top_emp = extract_top_employer(pdf_path) 
    rows.append({
        "Unit": UNIT_NAME,
        "Year": year,
        "Employer Names": top_emp if top_emp else ""  
    })

# Convert to DataFrame and export to CSV
df = pd.DataFrame(rows, columns=["Unit", "Year", "Employer Names"])
df.to_csv("top_employers_university_wide.csv", index=False)

