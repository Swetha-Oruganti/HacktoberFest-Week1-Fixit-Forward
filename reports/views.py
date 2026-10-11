import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from PIL import Image, ImageOps, UnidentifiedImageError

from .repository import collection, ping
from .services.classifier import ClassifierUnavailable, ISSUES, classify_image
from .services.reporting import iso_now, report_text

logger = logging.getLogger(__name__)
ALLOWED_STATUSES = {
    "ready_to_submit": "Ready to submit",
    "submitted_by_user": "Submitted by me",
    "acknowledged": "Acknowledged",
    "in_progress": "In progress",
    "resolved": "Resolved",
}
ALLOWED_SEVERITIES = {"low", "medium", "high", "urgent"}


def _json_body(request):
    try:
        if request.content_type and request.content_type.startswith("multipart/"):
            data = json.loads(request.POST.get("report", "{}"))
        else:
            data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Request body must be valid JSON.")
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def _valid_image(upload):
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    if upload.size == 0 or upload.size > limit:
        raise ValueError(f"Choose an image smaller than {settings.MAX_UPLOAD_MB} MB.")
    try:
        with Image.open(upload) as image:
            image.verify()
        upload.seek(0)
        with Image.open(upload) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Use a JPEG, PNG, or WebP image.")
            if image.width > 8000 or image.height > 8000:
                raise ValueError("Image dimensions must be 8000 × 8000 pixels or smaller.")
            image_format = image.format
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The uploaded file is not a supported image.") from exc
    upload.seek(0)
    return image_format


def _serialize(report):
    report["id"] = str(report.pop("_id"))
    if report.get("image_path"):
        report["photo_url"] = settings.MEDIA_URL + report["image_path"]
    for field in ("created_at", "updated_at"):
        if field in report and not isinstance(report[field], str):
            report[field] = report[field].isoformat()
    return report


@require_GET
def home(request):
    return render(request, "reports/index.html", {"max_upload_mb": settings.MAX_UPLOAD_MB})


@require_POST
def analyze(request):
    upload = request.FILES.get("photo")
    if upload is None:
        return JsonResponse({"error": "Choose a photo to analyze."}, status=400)
    try:
        _valid_image(upload)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    staging = settings.MEDIA_ROOT / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    temp_path = staging / f"{uuid.uuid4().hex}{Path(upload.name).suffix.lower()}"
    try:
        with temp_path.open("wb") as destination:
            for chunk in upload.chunks():
                destination.write(chunk)
        result = classify_image(temp_path, mode=settings.AI_MODE, model_name=settings.CLIP_MODEL)
        category = result["category"]
        draft = {
            "category": category,
            "category_label": result["category_label"],
            "department": result["department"],
            "confidence": result["confidence"],
            "classifier": result["classifier"],
            "model": result["model"],
            "severity": "medium",
            "title": result["category_label"],
            "description": (
                f"Please inspect the reported {result['category_label'].lower()} near the location below. "
                "The attached photo shows the condition observed. Please assess the issue and advise on the next steps."
            ),
        }
        return JsonResponse({"draft": draft})
    except ClassifierUnavailable as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except Exception:
        logger.exception("Image classification failed")
        return JsonResponse({"error": "Photo analysis failed. Try another image or choose heuristic demo mode."}, status=503)
    finally:
        temp_path.unlink(missing_ok=True)


@require_POST
def create_report(request):
    upload = request.FILES.get("photo")
    if upload is None:
        return JsonResponse({"error": "The report needs a photo."}, status=400)
    try:
        image_format = _valid_image(upload)
        data = _json_body(request)
        category = data.get("category", "other")
        if category not in ISSUES:
            raise ValueError("Choose a valid issue category.")
        title = str(data.get("title", "")).strip()[:120]
        description = str(data.get("description", "")).strip()[:2000]
        if not title or not description:
            raise ValueError("Add a short title and description before saving.")
        severity = data.get("severity", "medium")
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError("Choose a valid severity.")
        location = str(data.get("location", "")).strip()[:240]
        coordinates = data.get("coordinates") or {}
        if not isinstance(coordinates, dict):
            raise ValueError("Location coordinates are invalid.")
        latitude = coordinates.get("latitude")
        longitude = coordinates.get("longitude")
        if latitude is not None or longitude is not None:
            latitude, longitude = float(latitude), float(longitude)
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("Location coordinates are outside valid bounds.")
            coordinates = {"latitude": round(latitude, 6), "longitude": round(longitude, 6)}
        else:
            coordinates = None
    except (ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    image_id = uuid.uuid4().hex
    suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
    relative_image = f"reports/{image_id}{suffix}"
    image_path = settings.MEDIA_ROOT / relative_image
    image_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Re-encode so uploaded EXIF GPS/device metadata is not retained.
        with Image.open(upload) as source_image:
            clean_image = ImageOps.exif_transpose(source_image)
            if image_format == "JPEG":
                clean_image.convert("RGB").save(image_path, format="JPEG", quality=88, optimize=True)
            else:
                clean_image.save(image_path, format=image_format, optimize=True)
        now = iso_now()
        report = {
            "reference": f"FF-{datetime.utcnow():%y%m%d}-{image_id[:6].upper()}",
            "title": title,
            "description": description,
            "category": category,
            "category_label": ISSUES[category]["label"],
            "department": ISSUES[category]["department"],
            "severity": severity,
            "confidence": data.get("confidence") if isinstance(data.get("confidence"), (int, float)) else None,
            "classifier": str(data.get("classifier", "user-edited"))[:40],
            "location": location,
            "coordinates": coordinates,
            "image_path": relative_image,
            "status": "ready_to_submit",
            "status_history": [{"status": "ready_to_submit", "label": ALLOWED_STATUSES["ready_to_submit"], "at": now}],
            "created_at": now,
            "updated_at": now,
        }
        inserted = collection().insert_one(report)
        report["_id"] = inserted.inserted_id
        return JsonResponse({"report": _serialize(report)}, status=201)
    except Exception:
        image_path.unlink(missing_ok=True)
        logger.exception("Unable to save civic report")
        return JsonResponse({"error": "Could not save the report. Check that MongoDB is running and try again."}, status=503)


@require_GET
def list_reports(request):
    try:
        reports = [_serialize(row) for row in collection().find().sort("created_at", -1).limit(25)]
        return JsonResponse({"reports": reports})
    except Exception:
        logger.exception("Unable to list civic reports")
        return JsonResponse({"error": "MongoDB is unavailable."}, status=503)


@require_GET
def report_detail(request, report_id):
    if not ObjectId.is_valid(report_id):
        return JsonResponse({"error": "Report not found."}, status=404)
    report = collection().find_one({"_id": ObjectId(report_id)})
    if report is None:
        return JsonResponse({"error": "Report not found."}, status=404)
    if request.GET.get("format") == "txt":
        response = HttpResponse(report_text(report), content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{report["reference"]}.txt"'
        return response
    return JsonResponse({"report": _serialize(report)})


@require_POST
def update_status(request, report_id):
    if not ObjectId.is_valid(report_id):
        return JsonResponse({"error": "Report not found."}, status=404)
    try:
        data = _json_body(request)
        status = data.get("status")
        if status not in ALLOWED_STATUSES:
            raise ValueError("Choose a valid manual status.")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    now = iso_now()
    result = collection().update_one(
        {"_id": ObjectId(report_id)},
        {"$set": {"status": status, "updated_at": now}, "$push": {"status_history": {"status": status, "label": ALLOWED_STATUSES[status], "at": now}}},
    )
    if not result.matched_count:
        return JsonResponse({"error": "Report not found."}, status=404)
    report = collection().find_one({"_id": ObjectId(report_id)})
    return JsonResponse({"report": _serialize(report)})


@require_GET
def health(request):
    try:
        ping()
        return JsonResponse({"status": "ok", "database": "connected"})
    except Exception:
        return JsonResponse({"status": "degraded", "database": "unavailable"}, status=503)
