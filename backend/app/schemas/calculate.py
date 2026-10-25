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

class AIOption(str, Enum):
    OFF = "off"
    LIGHT = "light"  # Stable Diffusion XL, локальные LLM 7B
    HEAVY = "heavy"  # Training, большие LLM, ComfyUI

class Bottleneck(str, Enum):
    CPU = "CPU"
    GPU = "GPU"

class CalculateRequest(BaseModel):
    cpu_id: int = Field(gt=0)
    gpu_id: int = Field(gt=0)
    ram_id: int | None = Field(default=None, gt=0)
    ram_manual: dict | None = Field(default=None)  # {type, capacity_gb, channels}
    game: GameName
    mode: CalcMode
    budget: int | None = Field(default=None, ge=0)
    ai_mode: AIOption = Field(default=AIOption.OFF)
    sell_mode: str = Field(default="budget_only", pattern="^(budget_only|budget_plus_sell)$")

class CalculateResponse(BaseModel):
    bottleneck: Bottleneck
    current_fps: int
    upgraded_fps: int
    recommendation: str
    avg_price: int
    within_budget: bool = False
    upgrade_component: str | None = None
    ai_warning: str | None = None
    current_component_price: int = 0
    total_budget: int = 0
    mode: str = "budget_only"
    is_maxed_out: bool = False

class AutodetectRequest(BaseModel):
    cpu_name: str
    gpu_name: str

class AutodetectResponse(BaseModel):
    cpu_id: int | None
    cpu_name: str | None
    gpu_id: int | None
    gpu_name: str | None