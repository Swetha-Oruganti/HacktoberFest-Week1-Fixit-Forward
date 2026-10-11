# FixIt Forward

Turn an observation into a clear, editable civic issue report. Upload a photo, review a local AI suggestion, add an optional location, then save, copy, or download the report. Saving creates a draft in your own MongoDB instance; it does not submit anything to a civic authority.

## Features

- Local image analysis with an open-weight CLIP model (`openai/clip-vit-base-patch32`). The first run downloads model weights; after that, inference stays on this machine. Set `AI_MODE=heuristic` to disable model inference, or `AI_MODE=local` to require the model and fail clearly if it is unavailable.
- Editable issue type, title, description, and severity before a report is saved.
- Optional browser location, plus manual location/address entry.
- Reports saved to MongoDB with a manual status timeline and a generated printable/exportable report.
- Photo files stay on the app's media volume; only the report metadata and file path are stored in MongoDB.
- No login is required for the local demo. Do not expose this configuration to the public internet without adding authentication and deployment safeguards.

## Run locally

Requirements: Python 3.11+, MongoDB 7+, and (for local AI) enough disk space and memory for PyTorch and CLIP weights.

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Edit `.env` first if you need to change the MongoDB connection, secret key, or AI mode.

Open http://127.0.0.1:8000. For a quick demo without downloading AI weights, set `$env:AI_MODE = "heuristic"`. This uses transparent keyword heuristics and reports that mode in the UI; it is not AI inference. `AI_MODE=local` uses CLIP on-device and never sends the image to a commercial inference API. The model name can be changed with `CLIP_MODEL`; provide a compatible Hugging Face zero-shot image classification model.

For containers, `docker compose up --build` starts MongoDB and Django. The app is available at http://127.0.0.1:8000 and MongoDB data and uploads persist in named volumes.

## Data and privacy

Location is optional. Browser location is requested only after the person clicks the location button. Photo EXIF is not used to infer location. In local mode, image bytes are processed by the model in the app process. MongoDB stores report text, classification metadata, status history, and a relative image path; the image itself is stored in `media/`. Configure backup, access control, retention, and HTTPS before hosting real reports. Avoid uploading identifiable people, vehicle plates, or sensitive scenes.

## Project layout

- `reports/services/classifier.py`: replaceable local classifier adapter and deterministic demo fallback.
- `reports/services/reporting.py`: report formatting and authority-neutral report text.
- `reports/repository.py`: MongoDB persistence boundary.
- `reports/views.py`: upload analysis, report creation, status updates, exports, and app pages.
- `reports/static/reports/`: responsive user interface.

## Status tracking

Status updates are manual and stored as a timeline. The app has no civic authority integration and does not claim that a report has been submitted or acknowledged.

## Development

Install the dependencies above, run MongoDB, and use `python manage.py check`. No credentials are required for the local demonstration.
