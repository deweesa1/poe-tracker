"""Maps on the Atlas, for the League Start Mapping checklist.

The Atlas map pool rotates every league (about 28 maps out, 28 back in), so
the pool is listed per league. A map you run that isn't listed is added to the
checklist automatically, so a slightly off list fixes itself as you play.
Leagues without a list here show the maps you ran.
"""
from __future__ import annotations

# 3.29 Curse of the Allflame
POOL_329 = frozenset({
    'Academy', 'Alleyways', 'Ancient City', 'Arachnid Nest', 'Arachnid Tomb', 'Arcade', 'Arid Lake',
    'Armoury', 'Arsenal', 'Atoll', 'Basilica', 'Bazaar', 'Beach', 'Belfry', 'Bone Crypt', 'Bramble Valley',
    'Burial Chambers', 'Cage', 'Caldera', 'Cells', 'Cemetery', 'Channel', 'Chateau', 'City Square',
    'Cold River', 'Colonnade', 'Colosseum', 'Conservatory', 'Coral Ruins', 'Courthouse', 'Crater',
    'Crystal Ore', 'Dark Forest', 'Desert', 'Desert Spring', 'Dunes', 'Estuary', 'Excavation', 'Factory',
    'Fields', 'Flooded Mine', 'Forbidden Woods', 'Forking River', 'Foundry', 'Frozen Cabins',
    'Fungal Hollow', 'Gardens', 'Geode', 'Ghetto', 'Glacier', 'Grave Trough', 'Graveyard', 'Grotto',
    'Haunted Mansion', 'Iceberg', 'Infested Valley', 'Ivory Temple', 'Jungle Valley', 'Laboratory', 'Lair',
    'Lava Lake', 'Leyline', 'Lookout', 'Malformation', 'Marshes', 'Mausoleum', 'Mesa', 'Mineral Pools',
    'Museum', 'Orchard', 'Overgrown Shrine', 'Palace', 'Park', 'Peninsula', 'Phantasmagoria', 'Pier', 'Pit',
    'Plateau', 'Plaza', 'Port', 'Precinct', 'Primordial Blocks', 'Primordial Pool', 'Promenade', 'Ramparts',
    'Reef', 'Relic Chambers', 'Residence', 'Scriptorium', 'Shipyard', 'Shore', 'Shrine', 'Siege', 'Silo',
    'Spider Forest', 'Spider Lair', 'Stagnation', 'Strand', 'Sulphur Vents', 'Summit', 'Sunken City',
    'Temple', 'Terrace', 'Tower', 'Toxic Sewer', 'Tropical Island', 'Underground River', 'Vaal Pyramid',
    'Vaal Temple', 'Vault', 'Villa', 'Volcano', 'Waste Pool', 'Waterways',
})

# 3.29 brought these back and took these out; 3.28 Mirage is 3.29 the other way round
BACK_IN_329 = frozenset({
    'Arachnid Nest', 'Basilica', 'Bazaar', 'Caldera', 'Cells', 'Channel', 'Colonnade', 'Colosseum',
    'Conservatory', 'Crystal Ore', 'Desert', 'Desert Spring', 'Estuary', 'Forbidden Woods', 'Geode',
    'Infested Valley', 'Laboratory', 'Malformation', 'Museum', 'Phantasmagoria', 'Pier', 'Plateau',
    'Ramparts', 'Stagnation', 'Sunken City', 'Temple', 'Toxic Sewer', 'Vault',
})
OUT_IN_329 = frozenset({
    'Acid Caverns', 'Arena', 'Ashen Wood', 'Bog', 'Canyon', 'Carcass', 'Castle Ruins', 'Courtyard', 'Coves',
    'Crimson Temple', 'Crimson Township', 'Cursed Crypt', 'Defiled Cathedral', 'Dig', 'Dry Sea', 'Dungeon',
    'Lava Chamber', 'Lighthouse', 'Maze', 'Moon Temple', 'Mud Geyser', 'Necropolis', 'Pen', 'Racecourse',
    'Sepulchre', 'Underground Sea', 'Wasteland', 'Wharf',
})
POOL_328 = (POOL_329 - BACK_IN_329) | OUT_IN_329

ATLAS_POOLS = {"Curse of the Allflame": POOL_329, "Mirage": POOL_328}

# Unique maps: (name, area ids). Replica maps use the same area as the original,
# so the log can't tell them apart; they share a row.
UNIQUE_MAPS = [
    ("Acton's Nightmare", ["MapWorldsOvergrownShrineUnique"]),
    ("Caer Blaidd, Wolfpack's Den", ["MapWorldsUndergroundRiverUnique"]),
    ("Death and Taxes", ["MapWorldsNecropolisUnique"]),
    ("Doryani's Machinarium", ["MapWorldsMazeUnique"]),
    ("Hallowed Ground", ["MapWorldsCemeteryUnique"]),
    ("Maelström of Chaos", ["MapWorldsAtollUnique"]),
    ("Mao Kun", ["MapWorldsShoreUnique"]),
    ("Oba's Cursed Trove", ["MapWorldsTortureChamberUnique"]),
    ("Olmec's Sanctum", ["MapWorldsBoneCryptUnique"]),
    ("Pillars of Arun (or Replica)", ["MapWorldsDunesUnique"]),
    ("Poorjoy's Asylum (or Replica)", ["MapWorldsTempleUnique"]),
    ("The Coward's Trial", ["MapWorldsCursedCryptUnique"]),
    ("The Hall of Grandmasters", ["MapWorldsPromenadeUnique"]),
    ("The Putrid Cloister", ["MapWorldsMuseumUnique"]),
    ("The Twilight Temple", ["MapWorldsMoonTempleUnique"]),
    ("The Vinktar Square", ["MapWorldsCourtyardUnique"]),
    ("Vaults of Atziri", ["MapWorldsVaalPyramidUnique"]),
    ("Whakawairua Tuahu", ["MapWorldsStrandUnique"]),
    ("Cortex (or Replica)", ["Synthesis_MapBoss"]),
    ("Altered Distant Memory", ["Synthesis_MapGuardian1"]),
    ("Augmented Distant Memory", ["Synthesis_MapGuardian2"]),
    ("Twisted Distant Memory", ["Synthesis_MapGuardian3"]),
    ("Rewritten Distant Memory", ["Synthesis_MapGuardian4"]),
]

# Map areas that aren't regular Atlas maps (bosses, guardians, citadels, memories...).
NOT_REGULAR = ("Unique", "Boss", "Guardian", "Chimera", "Hydra", "Minotaur", "Phoenix", "ShapersRealm", "Harbinger",
               "Synthesised", "Trialmaster", "Sanctuary", "Citadel", "Fortress", "Abomination", "Ziggurat",
               "CourtyardOfWasting", "ChambersOfImpurity", "TheatreOfLies", "Memory", "Core", "Uber", "Ultimatum",
               "Elder", "Shaper", "Maven", "Exarch", "Eater")
