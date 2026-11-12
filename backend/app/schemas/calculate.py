from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.offers import Source

class GameName(str, Enum):
    CS2 = "CS2"
    DOTA2 = "Dota 2"
    CYBERPUNK = "Cyberpunk 2077"
    GTA5 = "GTA V"
    FORTNITE = "Fortnite"
    VALORANT = "Valorant"
    APEX = "Apex Legends"
    RDR2 = "Red Dead Redemption 2"
    PUBG = "PUBG: Battlegrounds"
    WARZONE = "Call of Duty: Warzone"
    OVERWATCH = "Overwatch 2"
    BG3 = "Baldur's Gate 3"
    HOGWARTS = "Hogwarts Legacy"
    STARFIELD = "Starfield"
    FORZA5 = "Forza Horizon 5"
    WITCHER3 = "The Witcher 3 Next-Gen"
    HELLDIVERS = "Helldivers 2"
    RE4 = "Resident Evil 4 Remake"
    MIR_TANKOV = "Мир танков"

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

class RamManual(BaseModel):
    type: Literal["DDR3", "DDR4", "DDR5"] | None = None
    capacity_gb: int = Field(ge=2, le=512)
    channels: Literal[1, 2] | None = None


class PlatformUpgradeSelection(BaseModel):
    cpu_id: int = Field(gt=0)
    motherboard_offer_id: int = Field(gt=0)
    memory_offer_id: int = Field(gt=0)
    cooler_offer_id: int = Field(gt=0)


from app.schemas.geography import GeoQuery

class CalculateRequest(GeoQuery):
    cpu_id: int = Field(gt=0)
    gpu_id: int = Field(gt=0)
    ram_id: int | None = Field(default=None, gt=0)
    ram_manual: RamManual | None = None
    game: GameName
    mode: CalcMode
    budget: int | None = Field(default=None, ge=0)
    ai_mode: AIOption = Field(default=AIOption.OFF)
    sell_mode: str = Field(default="budget_only", pattern="^(budget_only|budget_plus_sell)$")
    target_fps: int = Field(default=60, ge=1, le=1000)
    price_sources: list[Source] | None = Field(default=None, min_length=1, max_length=13)
    refresh_avito_prices: bool = False
    selected_upgrade_id: int | None = Field(default=None, gt=0)
    price_lookup_id: int | None = Field(default=None, gt=0)
    expected_sale_price: int | None = Field(default=None, ge=0, le=10000000)
    selected_platform: PlatformUpgradeSelection | None = None

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
    upgrade_price: dict | None = None
    upgrade_name: str | None = None
    upgrade_id: int | None = None
    target_fps: int = 60
    target_reached: bool = False
    current_fps_outlook: dict | None = None
    upgraded_fps_outlook: dict | None = None
    compatibility_notes: list[str] = Field(default_factory=list)
    alternatives: list[dict] = Field(default_factory=list)
    limiting_explanation: str | None = None
    price_search_status: list[dict] = Field(default_factory=list)
    price_search_summary: list[dict] = Field(default_factory=list)
    target_basis: Literal['central_estimate'] = 'central_estimate'
    resale_price: dict | None = None
    cash_budget: int = 0
    net_upgrade_cost: int | None = None
    upgrade_kind: Literal['single', 'platform'] | None = None
    upgrade_parts: list[dict] = Field(default_factory=list)
    platform_upgrade_note: str | None = None
    resale_status: Literal['disabled', 'estimated', 'manual', 'unavailable'] = 'disabled'
    resale_notice: str | None = None

class AutodetectRequest(BaseModel):
    cpu_name: str
    gpu_name: str

class AutodetectResponse(BaseModel):
    cpu_id: int | None
    cpu_name: str | None
    gpu_id: int | None
    gpu_name: str | None
