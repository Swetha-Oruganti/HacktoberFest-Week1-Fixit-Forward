"""Local image classification with a small, explicit demo fallback."""
from functools import lru_cache
from pathlib import Path

ISSUES = {
    "overflowing_bin": {"label": "Overflowing bin", "department": "Sanitation / Solid Waste"},
    "pothole": {"label": "Pothole or damaged road", "department": "Roads / Public Works"},
    "streetlight": {"label": "Broken streetlight", "department": "Street Lighting"},
    "sidewalk": {"label": "Damaged pavement or sidewalk", "department": "Roads / Public Works"},
    "drain": {"label": "Blocked drain or waterlogging", "department": "Stormwater / Drainage"},
    "public_space": {"label": "Neglected public space", "department": "Parks / Public Spaces"},
    "other": {"label": "Other civic issue", "department": "Local Civic Authority"},
}

LABEL_PROMPTS = [
    "an overflowing public waste bin or garbage pile",
    "a pothole or damaged road surface",
    "a broken or unlit streetlight",
    "a damaged pavement or sidewalk",
    "a blocked drain or street flooding",
    "a neglected park or public space",
    "another public infrastructure issue",
]
PROMPT_TO_KEY = dict(zip(LABEL_PROMPTS, ISSUES))


@lru_cache(maxsize=1)
def _pipeline(model_name):
    from transformers import pipeline
    return pipeline("zero-shot-image-classification", model=model_name, device=-1)


def classify_image(image_path: str | Path, *, mode: str, model_name: str) -> dict:
    """Return a stable civic taxonomy result; inference never leaves this process."""
    mode = (mode or "local").lower()
    if mode != "heuristic":
        try:
            result = _pipeline(model_name)(str(image_path), candidate_labels=LABEL_PROMPTS)
            prompt = result[0]["label"]
            key = PROMPT_TO_KEY.get(prompt, "other")
            return {
                "category": key,
                "category_label": ISSUES[key]["label"],
                "department": ISSUES[key]["department"],
                "confidence": round(float(result[0]["score"]), 3),
                "classifier": "local-open-weight",
                "model": model_name,
            }
        except Exception as exc:
            if mode == "local":
                raise ClassifierUnavailable(
                    "The local image model is not ready. Install its dependencies and download the model, "
                    "or set AI_MODE=heuristic for the transparent demo fallback."
                ) from exc

    # A predictable keyword fallback is useful for a no-download demo. It does
    # not inspect image pixels and is labeled honestly in every response.
    name = Path(image_path).name.lower()
    cues = {
        "overflowing_bin": ("bin", "garbage", "waste", "trash"),
        "pothole": ("pothole", "road"),
        "streetlight": ("light", "lamp"),
        "sidewalk": ("pavement", "sidewalk"),
        "drain": ("drain", "water"),
        "public_space": ("park", "public"),
    }
    key = next((issue for issue, words in cues.items() if any(word in name for word in words)), "other")
    return {
        "category": key,
        "category_label": ISSUES[key]["label"],
        "department": ISSUES[key]["department"],
        "confidence": 0.0,
        "classifier": "heuristic-demo",
        "model": None,
    }


class ClassifierUnavailable(RuntimeError):
    """Raised when required local model dependencies or weights are missing."""
