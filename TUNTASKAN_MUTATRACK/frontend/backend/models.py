from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class AnalysisFilesModel(BaseModel):
    r1: Optional[str] = None
    r2: Optional[str] = None
    reference: Optional[str] = None
    r1_name: Optional[str] = None
    r2_name: Optional[str] = None
    reference_name: Optional[str] = None
    r1_size: Optional[int] = 0
    r2_size: Optional[int] = 0
    reference_size: Optional[int] = 0
    annotation: Optional[str] = None
    annotation_name: Optional[str] = None
    annotation_size: Optional[int] = 0

class PipelineConfigModel(BaseModel):
    trim_quality: int = 20
    min_length: int = 50
    min_mapq: int = 20
    min_baseq: int = 20
    min_qual: float = 30
    min_depth: int = 10
    ploidy: int = 1
    snpeff_db: str = ""
    annotation_mode: str = "none"

class Config:
    extra = "allow"  # parameter tambahan dari frontend tidak ditolak

class AnalysisCreateRequest(BaseModel):
    id: Optional[str] = None
    nama: str
    organisme: Optional[str] = "Escherichia coli str. K-12 substr. MG1655"
    mode: str = "paired"
    config: Optional[PipelineConfigModel] = None
    files: Optional[AnalysisFilesModel] = None

class AnalysisValidateRequest(BaseModel):
    r1_path: str
    r2_path: Optional[str] = None
    reference_path: str
    mode: str = "paired"

class AnalysisSummaryResponse(BaseModel):
    id: str
    nama: str
    status: str
    stage: Optional[str] = None
    progress: int = 0
    mode: str
    config: Dict[str, Any]
    files: Dict[str, Any]
    stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    log_tail: Optional[str] = None
