from enum import Enum
from pydantic import BaseModel, Field

class GameName(str, Enum):
    CS2 = "CS2"
    DOTA2 = "Dota 2"
    CYBERPUNK = "Cyberpunk 2077"
    GTA5 = "GTA V"
    FORTNITE = "Fortnite"
    VALORANT = "Valorant"
    APEX = "Apex Legends"
    RDR2 = "Red Dead Redemption 2"

class CalcMode(str, Enum):
    MODE_1080P_LOW = "1080p_low"
    MODE_1080P_HIGH = "1080p_high"
    MODE_1440P_HIGH = "1440p_high"

class Bottleneck(str, Enum):
    CPU = "CPU"
    GPU = "GPU"

class CalculateRequest(BaseModel):
    cpu_id: int = Field(gt=0)
    gpu_id: int = Field(gt=0)
    game: GameName
    mode: CalcMode

class CalculateResponse(BaseModel):
    bottleneck: Bottleneck
    current_fps: int
    upgraded_fps: int
    recommendation: str
    avg_price: int

class AutodetectRequest(BaseModel):
    cpu_name: str
    gpu_name: str

class AutodetectResponse(BaseModel):
    cpu_id: int | None
    cpu_name: str | None
    gpu_id: int | None
    gpu_name: str | None