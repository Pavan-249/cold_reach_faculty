# Data directory

Create this folder if it is missing. The pipeline reads CSV exports from the `scout/` scrapers.

## Faculty CSVs

Each `*_faculty_all.csv` file should be UTF-8 CSV with at least:

- `name`: full name
- `email`: institutional email when known
- `bio`: free text used for personalization
- `source`: short label (for example `Allen`, `eScience`)
- `profile_link`: faculty page URL when available

Generate files by running the appropriate script under `scout/`, or adapt the columns to your own institution.

## Runtime files (created by the tools, gitignored)

- `sent_log.csv`: append-only log of successful sends
- `failed_outreach.csv`: failures with reasons
- `outreach_tracking.csv`: faculty-level status for inbox sync scripts
- `resume_paths.json`: optional map of logical resume filename to absolute PDF path
- `resumes_extracted.json`: optional cached text from `scout/extract_resumes.py`
