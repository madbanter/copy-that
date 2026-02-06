from pathlib import Path
from typing import List, Literal, Optional
import yaml
from pydantic import BaseModel, Field, field_validator

class Config(BaseModel):
    source_directory: Path
    destination_base: Path
    folder_format: str = "%Y%m%d"
    include_extensions: List[str] = Field(default_factory=lambda: [".jpg", ".cr3", ".mp4", ".xmp"])
    conflict_policy: Literal["skip", "overwrite", "rename"] = "skip"

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
