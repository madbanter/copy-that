import datetime
import os
import logging
import exifread
from pathlib import Path
from typing import Literal, Dict, Any, Optional

logger = logging.getLogger(__name__)

def get_exif_metadata(file_path: Path) -> Dict[str, str]:
    """
    Extract media metadata (Make, Model, Date Taken/Digitized) from images and videos.
    """
    metadata = {"make": "Unknown", "model": "Unknown", "date_taken": ""}
    suffix = file_path.suffix.lower()
    
    # Standard image formats (using ExifRead)
    if suffix in (".jpg", ".jpeg", ".tiff", ".cr2", ".cr3", ".arw", ".dng"):
        try:
            with open(file_path, "rb") as f:
                tags = exifread.process_file(f, details=False, stop_tag="EXIF DateTimeOriginal")
                if "Image Make" in tags: metadata["make"] = str(tags["Image Make"]).strip()
                if "Image Model" in tags: metadata["model"] = str(tags["Image Model"]).strip()
                if "EXIF DateTimeOriginal" in tags: metadata["date_taken"] = str(tags["EXIF DateTimeOriginal"]).strip()
        except Exception as e:
            logger.debug(f"Could not read EXIF from {file_path}: {e}")
            
    # Basic video metadata (Placeholder for future improvement, uses filesystem dates for now but can expand)
    # Most professional video tools use XMP or specific sidecars, but some metadata libraries can parse atoms.
    # For now, we just ensure videos are recognized as media.
    elif suffix in (".mp4", ".mov", ".m4v", ".avi"):
        # Future: Use a library like 'hachoir' or 'pymediainfo' for deep video inspection
        pass
        
    return metadata

def get_file_date(
    file_path: Path, 
    source: Literal["creation", "modification", "filename", "exif"] = "creation",
    filename_date_format: str = "%Y-%m-%d %H.%M.%S",
    exif_metadata: Optional[Dict[str, str]] = None
) -> datetime.datetime:
    """
    Get the creation, modification, filename-extracted, or EXIF date of a file.
    """
    if source == "exif":
        exif = exif_metadata if exif_metadata is not None else get_exif_metadata(file_path)
        date_str = exif.get("date_taken")
        if date_str:
            try:
                # EXIF date format is typically "YYYY:MM:DD HH:MM:SS"
                return datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                logger.warning(f"Could not parse EXIF date '{date_str}' from {file_path}")
        
        # Fallback to creation if EXIF fails
        source = "creation"

    if source == "filename":
        try:
            # Get a sample formatted string to determine the expected length
            sample_date = datetime.datetime(2000, 1, 1, 12, 0, 0)
            expected_length = len(sample_date.strftime(filename_date_format))
            
            # Extract the relevant part of the filename stem
            stem = file_path.stem
            if len(stem) >= expected_length:
                date_str = stem[:expected_length]
                return datetime.datetime.strptime(date_str, filename_date_format)
            else:
                raise ValueError(f"Filename stem '{stem}' is shorter than expected length {expected_length}")
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Could not parse date from filename '{file_path.name}' "
                f"using format '{filename_date_format}'. "
                f"Falling back to creation time. Error: {e}"
            )
            # Fall through to creation fallback
            source = "creation"

    stat = file_path.stat()
    
    if source == "modification":
        timestamp = stat.st_mtime
    else:
        # Default to creation
        try:
            # macOS/Darwin specific creation time
            timestamp = stat.st_birthtime
        except AttributeError:
            # Fallback to modification time for other systems
            timestamp = stat.st_mtime
    
    return datetime.datetime.fromtimestamp(timestamp)

def generate_destination_path(
    source_file: Path,
    source_root: Path,
    destination_base: Path,
    folder_format: str = "%Y%m%d",
    mode: Literal["date", "mirror"] = "date",
    date_source: Literal["creation", "modification", "filename", "exif"] = "creation",
    filename_date_format: str = "%Y-%m-%d %H.%M.%S",
    path_template: Optional[str] = None
) -> Path:
    """
    Generate the destination path based on the selected mode or template.
    """
    if not path_template:
        if mode == "mirror":
            relative_path = source_file.relative_to(source_root)
            return destination_base / relative_path
        else:
            # Legacy 'date' mode
            exif = get_exif_metadata(source_file) if date_source == "exif" else None
            date = get_file_date(source_file, date_source, filename_date_format, exif_metadata=exif)
            subfolder_name = date.strftime(folder_format)
            return destination_base / subfolder_name / source_file.name

    # Template-based mode needs EXIF for make/model tokens regardless of date_source
    exif = get_exif_metadata(source_file)
    date = get_file_date(source_file, date_source, filename_date_format, exif_metadata=exif)
    
    context = {
        "year": date.strftime("%Y"),
        "month": date.strftime("%m"),
        "day": date.strftime("%d"),
        "hour": date.strftime("%H"),
        "minute": date.strftime("%M"),
        "second": date.strftime("%S"),
        "ext": source_file.suffix.lstrip("."),
        "filename": source_file.stem,
        "make": exif["make"],
        "model": exif["model"],
    }
    
    try:
        rendered_path = path_template.format(**context)
        return destination_base / rendered_path
    except KeyError as e:
        logger.error(f"Template error: missing token {e}")
        # Fallback to simple date-based if template fails
        subfolder_name = date.strftime(folder_format)
        return destination_base / subfolder_name / source_file.name
