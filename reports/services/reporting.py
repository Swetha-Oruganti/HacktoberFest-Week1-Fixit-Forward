from datetime import datetime


def report_text(report):
    location = report.get("location") or "Not provided"
    coords = report.get("coordinates") or {}
    if coords.get("latitude") is not None and coords.get("longitude") is not None:
        location = f"{location} ({coords['latitude']}, {coords['longitude']})"
    return "\n".join([
        "CIVIC ISSUE REPORT — prepared for the resident to submit",
        "",
        f"Reference: {report.get('reference', 'Draft')}",
        f"Issue: {report.get('title', '')}",
        f"Category: {report.get('category_label', '')}",
        f"Suggested department: {report.get('department', 'Local Civic Authority')}",
        f"Severity: {report.get('severity', 'Needs review').replace('_', ' ').title()}",
        f"Location: {location}",
        f"Observed: {report.get('observed_at', 'Not provided')}",
        "",
        "Description",
        report.get("description", ""),
        "",
        "This report was prepared with FixIt Forward. It has not been submitted to or verified by a civic authority.",
    ])


def iso_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
