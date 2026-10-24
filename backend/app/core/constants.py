from app.schemas.calculate import CalcMode, GameName

GAME_PROFILES = {
    GameName.CS2: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.019, "gpu": 0.021, "overhead": 0.97},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.014, "gpu": 0.016, "overhead": 0.97},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.012, "gpu": 0.013, "overhead": 0.97},
    },
    GameName.DOTA2: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.010, "gpu": 0.012, "overhead": 0.95},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.008, "gpu": 0.010, "overhead": 0.95},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.007, "gpu": 0.008, "overhead": 0.95},
    },
    GameName.CYBERPUNK: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.012, "gpu": 0.005, "overhead": 0.95},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.010, "gpu": 0.0033, "overhead": 0.97},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.008, "gpu": 0.0025, "overhead": 0.97},
    },
    GameName.GTA5: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.015, "gpu": 0.018, "overhead": 0.95},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.010, "gpu": 0.012, "overhead": 0.95},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.008, "gpu": 0.009, "overhead": 0.95},
    },
    GameName.FORTNITE: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.020, "gpu": 0.022, "overhead": 0.95},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.012, "gpu": 0.014, "overhead": 0.95},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.010, "gpu": 0.011, "overhead": 0.95},
    },
    GameName.VALORANT: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.030, "gpu": 0.025, "overhead": 0.98},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.022, "gpu": 0.020, "overhead": 0.98},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.018, "gpu": 0.016, "overhead": 0.98},
    },
    GameName.APEX: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.015, "gpu": 0.018, "overhead": 0.95},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.010, "gpu": 0.012, "overhead": 0.95},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.008, "gpu": 0.010, "overhead": 0.95},
    },
    GameName.RDR2: {
        CalcMode.MODE_1080P_LOW: {"cpu": 0.010, "gpu": 0.008, "overhead": 0.95},
        CalcMode.MODE_1080P_HIGH: {"cpu": 0.008, "gpu": 0.005, "overhead": 0.95},
        CalcMode.MODE_1440P_HIGH: {"cpu": 0.006, "gpu": 0.004, "overhead": 0.95},
    },
}

UPGRADE_GAIN = 1.35
MOCK_AVG_PRICE_RUB = 7000