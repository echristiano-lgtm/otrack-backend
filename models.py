from pydantic import BaseModel
from typing import Dict, List, Optional

class Split(BaseModel):
    seq: int
    code: str
    split: Optional[float] = None
    cum: Optional[float] = None

class Competitor(BaseModel):
    id: str
    name: str
    club: Optional[str] = None
    status: Optional[str] = None
    pos: Optional[str] = None
    timeS: Optional[float] = None
    splits: List[Split] = []

class ClassData(BaseModel):
    name: str
    competitors: List[Competitor] = []

class EventData(BaseModel):
    id: str
    name: str
    date: Optional[str] = None
    classes: Dict[str, ClassData]
