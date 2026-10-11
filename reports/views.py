import json
import hashlib
import logging
import mimetypes
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from bson import ObjectId
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from PIL import Image, ImageOps, UnidentifiedImageError
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument

from .repository import auth_attempts_collection, collection, ping, users_collection
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
DUMMY_PASSWORD_HASH = make_password("invalid-login-placeholder")


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
        report["photo_url"] = f"/api/reports/{report['id']}/photo/"
    report.pop("owner_id", None)
    for field in ("created_at", "updated_at"):
        if field in report and not isinstance(report[field], str):
            report[field] = report[field].isoformat()
    return report


@require_GET
def home(request):
    user = _current_user(request)
    return render(request, "reports/index.html", {
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "user": user,
    })


def _current_user(request):
    user_id = request.session.get("user_id")
    if not user_id or not ObjectId.is_valid(user_id):
        return None
    user = users_collection().find_one({"_id": ObjectId(user_id)}, {"display_name": 1, "email": 1})
    if user is None:
        request.session.flush()
        return None
    return {"id": str(user["_id"]), "display_name": user["display_name"], "email": user["email"]}


def login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = _current_user(request)
        if user is None:
            return JsonResponse({"error": "Sign in to continue."}, status=401)
        request.user_profile = user
        return view(request, *args, **kwargs)
    return wrapped


def _rate_limit_count(key):
    attempts = auth_attempts_collection()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = attempts.find_one({"_id": key})
    if row is None or row["expires_at"] <= now:
        attempts.replace_one(
            {"_id": key},
            {"_id": key, "count": 1, "expires_at": now + timedelta(minutes=15)},
            upsert=True,
        )
        return 1
    row = attempts.find_one_and_update(
        {"_id": key, "expires_at": {"$gt": now}},
        {"$inc": {"count": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return row["count"] if row else _rate_limit_count(key)


def _auth_is_limited(request, email, action):
    remote_ip = request.META.get("REMOTE_ADDR", "unknown")
    identity_key = hashlib.sha256(f"{action}:{email}:{remote_ip}".encode()).hexdigest()
    ip_key = hashlib.sha256(f"{action}:ip:{remote_ip}".encode()).hexdigest()
    identity_limit, ip_limit = (5, 18) if action == "register" else (8, 30)
    return _rate_limit_count(identity_key) > identity_limit or _rate_limit_count(ip_key) > ip_limit


@require_POST
def register(request):
    try:
        data = _json_body(request)
        display_name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = data.get("password", "")
        confirmation = data.get("password_confirmation", "")
        if not display_name or len(display_name) > 60:
            raise ValueError("Enter a name with 1 to 60 characters.")
        if len(email) > 254:
            raise ValueError("Enter a valid email address.")
        try:
            validate_email(email)
        except ValidationError as exc:
            raise ValueError("Enter a valid email address.") from exc
        if not isinstance(password, str) or len(password) < 12:
            raise ValueError("Use a password with at least 12 characters.")
        if len(password) > 256:
            raise ValueError("Password must be 256 characters or fewer.")
        if password != confirmation:
            raise ValueError("Those passwords do not match.")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        if _auth_is_limited(request, email, "register"):
            return JsonResponse({"error": "Too many sign-up attempts. Try again in 15 minutes."}, status=429)
        result = users_collection().insert_one({
            "display_name": display_name,
            "email": email,
            "email_normalized": email,
            "password_hash": make_password(password),
            "created_at": datetime.now(timezone.utc),
        })
        request.session.flush()
        request.session["user_id"] = str(result.inserted_id)
        return JsonResponse({"user": {"id": str(result.inserted_id), "display_name": display_name, "email": email}}, status=201)
    except DuplicateKeyError:
        return JsonResponse({"error": "An account with that email already exists. Sign in instead."}, status=409)
    except Exception:
        logger.exception("Account registration failed")
        return JsonResponse({"error": "Could not create your account. Check the database connection and try again."}, status=503)


@require_POST
def login_view(request):
    try:
        data = _json_body(request)
        email = str(data.get("email", "")).strip().lower()
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 256:
            password = ""
        if not email or len(email) > 254:
            raise ValueError("Enter your email and password.")
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    try:
        if _auth_is_limited(request, email, "login"):
            return JsonResponse({"error": "Too many sign-in attempts. Try again in 15 minutes."}, status=429)
        user = users_collection().find_one({"email_normalized": email})
        password_hash = user["password_hash"] if user else DUMMY_PASSWORD_HASH
        if not check_password(password, password_hash) or user is None:
            return JsonResponse({"error": "Email or password is incorrect."}, status=401)
        request.session.flush()
        request.session["user_id"] = str(user["_id"])
        auth_attempts_collection().delete_many({"_id": {"$in": [
            hashlib.sha256(f"login:{email}:{request.META.get('REMOTE_ADDR', 'unknown')}".encode()).hexdigest(),
            hashlib.sha256(f"login:ip:{request.META.get('REMOTE_ADDR', 'unknown')}".encode()).hexdigest(),
        ]}})
        return JsonResponse({"user": {"id": str(user["_id"]), "display_name": user["display_name"], "email": user["email"]}})
    except Exception:
        logger.exception("Account sign-in failed")
        return JsonResponse({"error": "Could not sign in. Check the database connection and try again."}, status=503)


@require_POST
@login_required
def logout_view(request):
    request.session.flush()
    return JsonResponse({"ok": True})


@require_POST
@login_required
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
@login_required
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
            "owner_id": ObjectId(request.user_profile["id"]),
        }
        inserted = collection().insert_one(report)
        report["_id"] = inserted.inserted_id
        return JsonResponse({"report": _serialize(report)}, status=201)
    except Exception:
        image_path.unlink(missing_ok=True)
        logger.exception("Unable to save civic report")
        return JsonResponse({"error": "Could not save the report. Check that MongoDB is running and try again."}, status=503)


@require_GET
@login_required
def list_reports(request):
    try:
        reports = [_serialize(row) for row in collection().find({"owner_id": ObjectId(request.user_profile["id"])}).sort("created_at", -1).limit(25)]
        return JsonResponse({"reports": reports})
    except Exception:
        logger.exception("Unable to list civic reports")
        return JsonResponse({"error": "MongoDB is unavailable."}, status=503)


@require_GET
@login_required
def report_detail(request, report_id):
    if not ObjectId.is_valid(report_id):
        return JsonResponse({"error": "Report not found."}, status=404)
    report = collection().find_one({"_id": ObjectId(report_id), "owner_id": ObjectId(request.user_profile["id"])})
    if report is None:
        return JsonResponse({"error": "Report not found."}, status=404)
    if request.GET.get("format") == "txt":
        response = HttpResponse(report_text(report), content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{report["reference"]}.txt"'
        return response
    return JsonResponse({"report": _serialize(report)})


@require_POST
@login_required
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
        {"_id": ObjectId(report_id), "owner_id": ObjectId(request.user_profile["id"])},
        {"$set": {"status": status, "updated_at": now}, "$push": {"status_history": {"status": status, "label": ALLOWED_STATUSES[status], "at": now}}},
    )
    if not result.matched_count:
        return JsonResponse({"error": "Report not found."}, status=404)
    report = collection().find_one({"_id": ObjectId(report_id), "owner_id": ObjectId(request.user_profile["id"])})
    return JsonResponse({"report": _serialize(report)})


@require_GET
@login_required
def report_photo(request, report_id):
    if not ObjectId.is_valid(report_id):
        return JsonResponse({"error": "Report not found."}, status=404)
    report = collection().find_one({"_id": ObjectId(report_id), "owner_id": ObjectId(request.user_profile["id"])})
    if report is None:
        return JsonResponse({"error": "Report not found."}, status=404)
    media_root = settings.MEDIA_ROOT.resolve()
    photo_path = (media_root / report.get("image_path", "")).resolve()
    if not photo_path.is_relative_to(media_root) or not photo_path.is_file():
        return JsonResponse({"error": "Photo not found."}, status=404)
    content_type = mimetypes.guess_type(photo_path.name)[0] or "application/octet-stream"
    response = FileResponse(photo_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def health(request):
    try:
        ping()
        return JsonResponse({"status": "ok", "database": "connected"})
    except Exception:
        return JsonResponse({"status": "degraded", "database": "unavailable"}, status=503)
