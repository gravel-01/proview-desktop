# Resume Compatibility Test Suite

This suite targets regression risks for resume parsing compatibility in the interview system.

## Included
- `test_resume_text_extraction.py`
- `test_resume_compatibility_tracking.py`
- Runner: `run_resume_compat_suite.py`

## Quick Run
```powershell
cd D:\proview-desktop\proview-desktop\backend
python tests\run_resume_compat_suite.py
```

## Artifacts
After execution, reports are generated under:
- `tests/artifacts/resume-compat-results.json`
- `tests/artifacts/resume-compat-report.md`

## Typical Usage
- Run before merging resume/OCR related changes.
- Attach Markdown report in compatibility tracking issue.

