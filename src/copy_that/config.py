from pathlib import Path
from typing import List, Literal, Optional
import yaml
from pydantic import BaseModel, Field, field_validator

class Config(BaseModel):
    source_directory: Path
    destination_base: Path
    folder_format: str = "%Y%m%d"
    include_extensions: List[str] = Field(default_factory=lambda: [".jpg", ".jpeg", ".cr3", ".arw", ".dng", ".mp4", ".xmp"])
    conflict_policy: Literal["skip", "overwrite", "rename"] = "skip"
    verification_method: Literal["none", "size", "md5", "sha1"] = "none"

    @field_validator("include_extensions", mode="before")
    @classmethod
    def normalize_extensions(cls, v: List[str]) -> List[str]:
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
