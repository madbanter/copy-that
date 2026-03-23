from pathlib import Path
from typing import List, Literal, Optional, Any, Dict
import yaml
import logging
import datetime
from pydantic import BaseModel, Field, field_validator, ValidationError

logger = logging.getLogger(__name__)

class Config(BaseModel):
    source_directory: Path
    destination_base: Path
    folder_format: str = "%Y%m%d"
    organization_mode: Literal["date", "mirror"] = "date"
    date_source: Literal["creation", "modification", "filename"] = "creation"
    filename_date_format: str = "%Y-%m-%d %H.%M.%S"
    include_extensions: List[str] = Field(default_factory=lambda: [".jpg", ".jpeg", ".cr3", ".arw", ".dng", ".mp4", ".xmp"])
    conflict_policy: Literal["skip", "overwrite", "rename"] = "skip"
    verification_method: Literal["none", "size", "md5", "sha1"] = "none"
    verification_failure_behavior: Literal["retry", "ignore", "delete"] = "retry"
    output_verbosity: Literal["minimal", "normal", "verbose"] = "normal"
    log_file: Optional[Path] = None
    max_log_size: int = 10 * 1024 * 1024  # 10 MB
    log_backup_count: int = 5
    pre_sync_space_check: bool = False
    max_workers: Optional[int] = None
    buffer_size: int = Field(default=1024 * 1024, ge=1024, le=128 * 1024 * 1024)

    @field_validator("include_extensions", mode="before")
    @classmethod
    def normalize_extensions(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            return v
        return [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in v]

    @field_validator("source_directory", "destination_base")
    @classmethod
    def expand_paths(cls, v: Path) -> Path:
        return v.expanduser().resolve()

    @field_validator("filename_date_format")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            # Test it with a sample date. strftime is often too lenient.
            # strptime is stricter because it must be a valid format that can parse back.
            now = datetime.datetime.now().replace(microsecond=0)
            s = now.strftime(v)
            datetime.datetime.strptime(s, v)
            return v
        except Exception as e:
            raise ValueError(f"Invalid date format string: {v}. Error: {e}")

def find_config() -> Optional[Path]:
    """
    Search for configuration files in standard locations.
    Order:
    1. ./config.yaml or ./config.yml
    2. ~/.config/copy-that/config.yaml
    3. ~/.copy-that.yaml
    """
    search_paths = [
        Path("config.yaml"),
        Path("config.yml"),
        Path("~/.config/copy-that/config.yaml"),
        Path("~/.copy-that.yaml"),
    ]
    
    for path in search_paths:
        try:
            resolved_path = path.expanduser().resolve()
            if resolved_path.exists():
                return resolved_path
        except (OSError, PermissionError):
            # If we can't access a directory in the search path, skip it
            continue
    return None

def merge_config(config_path: Optional[Path] = None, **kwargs: Any) -> Config:
    """
    Load config from YAML (if it exists) and merge with CLI overrides.
    CLI overrides (provided via kwargs) take precedence if they are not None.
    
    If config_path is provided but does not exist, raises FileNotFoundError.
    If config_path is None, it searches standard locations via find_config().
    
    Relative paths in the YAML file are resolved relative to the configuration file's location.
    """
    data: Dict[str, Any] = {}
    actual_config_path: Optional[Path] = None

    if config_path:
        if not config_path.exists():
            raise FileNotFoundError(f"Explicitly provided configuration file not found: {config_path}")
        actual_config_path = config_path.resolve()
    else:
        actual_config_path = find_config()
    
    if actual_config_path:
        logger.info(f"Loading configuration from {actual_config_path}")
        try:
            with open(actual_config_path, "r") as f:
                yaml_data = yaml.safe_load(f)
                if yaml_data:
                    # Resolve relative paths in the YAML relative to the config file's directory
                    config_dir = actual_config_path.parent
                    for key in ["source_directory", "destination_base"]:
                        if key in yaml_data and yaml_data[key]:
                            path_val = Path(yaml_data[key])
                            if not path_val.is_absolute():
                                # expanduser handles ~ in the YAML file too
                                yaml_data[key] = (config_dir / path_val.expanduser()).resolve()
                    data.update(yaml_data)
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing configuration file {actual_config_path}: {e}")
        except OSError as e:
            raise OSError(f"Could not read configuration file {actual_config_path}: {e}")
    else:
        logger.debug("No configuration file found in standard locations.")
    
    # Update with CLI overrides only if they are not None
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value
            
    try:
        return Config(**data)
    except ValidationError as e:
        missing_fields = [str(err["loc"][0]) for err in e.errors() if err["type"] == "missing"]
        if missing_fields:
            if not actual_config_path:
                raise ValueError(
                    f"No configuration file found and required arguments are missing: {', '.join(missing_fields)}. "
                    "Please provide a config file or use CLI options (--source, --dest)."
                ) from e
            else:
                raise ValueError(
                    f"Configuration from {actual_config_path} is missing required fields: {', '.join(missing_fields)}"
                ) from e
        raise ValueError(f"Invalid configuration: {e}") from e
