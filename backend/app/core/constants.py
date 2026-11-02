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

# Fallback GPU and CPU-throughput coefficients. Published GPU observations in
# game_benchmarks.json override the GPU estimate where coverage exists.
ESTIMATED_GAME_PROFILES = {
    GameName.MIR_TANKOV: ((.020, .020), (.014, .012), (.012, .0085)),
    GameName.PUBG: ((.013, .012), (.010, .008), (.008, .0058)),
    GameName.WARZONE: ((.009, .007), (.007, .0045), (.006, .0032)),
    GameName.OVERWATCH: ((.020, .022), (.016, .015), (.013, .010)),
    GameName.BG3: ((.010, .0075), (.008, .0048), (.0065, .0033)),
    GameName.HOGWARTS: ((.009, .005), (.007, .0032), (.0055, .0023)),
    GameName.STARFIELD: ((.007, .0038), (.0055, .0026), (.0045, .0018)),
    GameName.FORZA5: ((.012, .010), (.009, .0065), (.0075, .0046)),
    GameName.WITCHER3: ((.012, .008), (.009, .005), (.007, .0035)),
    GameName.HELLDIVERS: ((.008, .0055), (.006, .0038), (.005, .0027)),
    GameName.RE4: ((.012, .010), (.009, .0065), (.007, .0045)),
}
for game, modes in ESTIMATED_GAME_PROFILES.items():
    GAME_PROFILES[game] = {mode: {'cpu': cpu, 'gpu': gpu, 'overhead': .95}
                           for mode, (cpu, gpu) in zip(CalcMode, modes)}
