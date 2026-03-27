import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = "generated_backend"


async def project_builder(files: dict) -> str:
    """
    Write a dictionary of {relative_path: content} to disk
    under a clean `generated_backend/` folder.

    Parameters
    ----------
    files:
        Keys   — relative file paths  (e.g. "app/main.py")
        Values — file contents as str (empty string for __init__ stubs)

    Returns
    -------
    Absolute path to the generated project folder.

    Raises
    ------
    ValueError  — if `files` is empty or contains invalid entries.
    OSError     — if any file/directory operation fails.
    """
    if not files:
        raise ValueError("files dict must not be empty.")

    root = Path(OUTPUT_DIR).resolve()

    # Wipe and recreate so every build is clean
    if root.exists():
        shutil.rmtree(root)
        logger.info("project_builder | removed existing %s", root)

    root.mkdir(parents=True, exist_ok=False)
    logger.info("project_builder | created root %s", root)

    written: list[str] = []
    errors:  list[str] = []

    for raw_path, content in files.items():
        # --- validate entry -------------------------------------------------
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"Skipped invalid key: {raw_path!r}")
            logger.warning("project_builder | invalid key %r — skipping", raw_path)
            continue

        if not isinstance(content, str):
            errors.append(f"Skipped non-string content for: {raw_path!r}")
            logger.warning("project_builder | non-string content for %r — skipping", raw_path)
            continue

        # --- resolve destination, guard against path traversal --------------
        target = (root / raw_path.strip()).resolve()
        if not str(target).startswith(str(root)):
            errors.append(f"Blocked path traversal attempt: {raw_path!r}")
            logger.error("project_builder | path traversal blocked for %r", raw_path)
            continue

        # --- create parent directories ---------------------------------------
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(f"Could not create directory {target.parent}: {exc}")
            logger.error("project_builder | mkdir failed for %s: %s", target.parent, exc)
            continue

        # --- write file atomically via a temp sibling -----------------------
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(target)
            written.append(str(target.relative_to(root)))
            logger.debug("project_builder | wrote %s", target.relative_to(root))
        except OSError as exc:
            errors.append(f"Could not write {raw_path}: {exc}")
            logger.error("project_builder | write failed for %s: %s", target, exc)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    logger.info(
        "project_builder | done — %d written, %d skipped/errored",
        len(written), len(errors),
    )

    if errors:
        logger.warning("project_builder | issues encountered:\n%s", "\n".join(errors))

    if not written:
        raise OSError(f"No files were written. Errors: {errors}")

    return str(root)
