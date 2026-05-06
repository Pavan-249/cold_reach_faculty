#!/usr/bin/env python3
"""Fetch 25 more Public Health faculty from SPH Core with emails from facbio pages."""
import csv
import os
import re
import time
import urllib.request

try:
    import requests
    def get_url(url):
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.text
except ImportError:
    def get_url(url):
        req = urllib.request.urlopen(url, timeout=20)
        return req.read().decode()

SPH_CORE_URL = "https://sph.washington.edu/faculty/sphcore"
FACBIO_BASE = "https://sph.washington.edu/faculty/facbio"
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PUBLICHEALTH_CSV = os.path.join(DATA_DIR, "publichealth_faculty_all.csv")


def load_existing_names():
    existing = set()
    if os.path.exists(PUBLICHEALTH_CSV):
        with open(PUBLICHEALTH_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("name") or "").strip().strip('"')
                if name:
                    existing.add(name.lower())
                    # also add reversed "Last, First" for matching
                    parts = name.split()
                    if len(parts) >= 2:
                        existing.add(f"{parts[-1]}, {' '.join(parts[:-1])}".lower())
    return existing


def slug_to_name(slug):
    """Convert facbio slug like Abbott_Collette or Chan_Kwun_Chuen to 'Collette Abbott' (title case)."""
    parts = slug.split("_")
    if len(parts) >= 2:
        first = " ".join(parts[1:])
        last = parts[0]
        name = f"{first} {last}".strip()
        return name.title() if name else slug.replace("_", " ")
    return slug.replace("_", " ").title()


def parse_sph_core_html(html):
    """Extract faculty facbio slugs from SPH Core page HTML."""
    # Links like href="/faculty/facbio/Abbott_Collette"
    pattern = r'href="(?:https://sph\.washington\.edu)?/faculty/facbio/([^"]+)"'
    slugs = re.findall(pattern, html)
    seen = set()
    results = []
    for slug in slugs:
        if slug in seen:
            continue
        seen.add(slug)
        name = slug_to_name(slug)
        results.append({"name": name, "slug": slug})
    return results


def fetch_email_from_facbio(slug):
    """Fetch facbio page and extract email (mailto or @uw.edu)."""
    url = f"{FACBIO_BASE}/{slug}"
    try:
        text = get_url(url)
        # mailto:xxx@uw.edu
        m = re.search(r"mailto:([a-zA-Z0-9._%+-]+@(?:uw\.edu|washington\.edu))", text)
        if m:
            return m.group(1).strip().lower()
        # plain email
        m = re.search(r"[a-zA-Z0-9._%+-]+@(?:uw\.edu|washington\.edu)", text)
        if m:
            return m.group(0).strip().lower()
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
    return ""


def name_matches_existing(full_name, existing_names):
    """Check if this faculty is already in our CSV (by full name or Last, First)."""
    n = full_name.strip().lower()
    if n in existing_names:
        return True
    parts = n.split()
    if len(parts) >= 2:
        last_first = f"{parts[-1]}, {' '.join(parts[:-1])}".lower()
        if last_first in existing_names:
            return True
    return False


def main():
    existing = load_existing_names()
    print(f"Existing faculty in CSV: {len(existing)}")

    print("Fetching SPH Core page...")
    try:
        html = get_url(SPH_CORE_URL)
    except Exception as e:
        print(f"Failed to fetch SPH Core: {e}")
        return

    faculty = parse_sph_core_html(html)
    print(f"Parsed {len(faculty)} faculty from SPH Core")

    # Filter to new only, take 25
    new_ones = []
    for f in faculty:
        if name_matches_existing(f["name"], existing):
            continue
        new_ones.append(f)
        if len(new_ones) >= 25:
            break

    if not new_ones:
        print("No new faculty found (all already in CSV).")
        return

    print(f"Fetching emails for {len(new_ones)} new faculty...")
    rows = []
    for i, f in enumerate(new_ones):
        email = fetch_email_from_facbio(f["slug"])
        profile_link = f"{FACBIO_BASE}/{f['slug']}"
        bio = (f.get("title") or "Faculty, School of Public Health").strip()[:200]
        rows.append({
            "name": f["name"],
            "email": email,
            "bio": bio,
            "profile_link": profile_link,
            "source": "Public Health",
        })
        print(f"  {i+1}. {f['name']} -> {email or '(no email)'}")
        time.sleep(0.5)

    # Append to CSV
    file_exists = os.path.exists(PUBLICHEALTH_CSV)
    with open(PUBLICHEALTH_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "bio", "profile_link", "source"])
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Appended {len(rows)} faculty to {PUBLICHEALTH_CSV}")


if __name__ == "__main__":
    main()
