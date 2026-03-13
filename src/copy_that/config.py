from pathlib import Path
from typing import List, Literal, Optional
import yaml
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional, Any, Dict

class Config(BaseModel):
    source_directory: Path
    destination_base: Path
    folder_format: str = "%Y%m%d"
    organization_mode: Literal["date", "mirror"] = "date"
    date_source: Literal["creation", "modification"] = "creation"
    include_extensions: List[str] = Field(default_factory=lambda: [".jpg", ".jpeg", ".cr3", ".arw", ".dng", ".mp4", ".xmp"])
    conflict_policy: Literal["skip", "overwrite", "rename"] = "skip"
    verification_method: Literal["none", "size", "md5", "sha1"] = "none"
    verification_failure_behavior: Literal["retry", "ignore", "delete"] = "retry"
    pre_sync_space_check: bool = False
    max_workers: Optional[int] = None

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

def load_config(config_path: Path) -> Config:
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
    
    return Config(**data)

def merge_config(config_path: Optional[Path], **kwargs: Any) -> Config:
    """
    Load config from YAML (if it exists) and merge with CLI overrides.
    CLI overrides (provided via kwargs) take precedence if they are not None.
    """
    data: Dict[str, Any] = {}
    
    if config_path and config_path.exists():
        with open(config_path, "r") as f:
            yaml_data = yaml.safe_load(f)
            if yaml_data:
                data.update(yaml_data)
    
    # Update with CLI overrides only if they are not None
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value
            
    return Config(**data)
