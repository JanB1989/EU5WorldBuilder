# Verified location-property audit

Date: 2026-09-14. Read-only audit of installed vanilla definitions, native GUI and exported trigger documentation. No game or map values changed.

## Location template fields

Parsed 28,573 location templates. Complete top-level field inventory:

| Field | Locations explicitly containing it |

|---|---:|

| `topography` | 28,573 |

| `vegetation` | 22,864 |

| `climate` | 28,573 |

| `religion` | 20,929 |

| `culture` | 20,922 |

| `raw_material` | 20,929 |

| `natural_harbor_suitability` | 4,418 |

| `modifier` | 101 |

| `movement_assistance` | 749 |

## climates

Definitions: `tropical`, `subtropical`, `oceanic`, `arid`, `cold_arid`, `mediterranean`, `continental`, `arctic`.

Scalar configuration fields (complete, including presentation and movement settings):

- `tropical`: {"winter": "none", "color": "climate_tropical", "colonial_migration_size_modifier": -0.33, "debug_color": "rgb"}

- `subtropical`: {"winter": "none", "color": "climate_subtropical", "debug_color": "rgb"}

- `oceanic`: {"winter": "mild", "color": "climate_oceanic", "debug_color": "rgb"}

- `arid`: {"winter": "none", "color": "climate_arid", "has_precipitation": false, "debug_color": "rgb"}

- `cold_arid`: {"winter": "mild", "color": "climate_cold_arid", "has_precipitation": false, "debug_color": "hsv360"}

- `mediterranean`: {"winter": "none", "color": "climate_mediterranean", "colonial_migration_size_modifier": 0.1, "debug_color": "rgb"}

- `continental`: {"winter": "normal", "color": "climate_continental", "debug_color": "hsv360"}

- `arctic`: {"winter": "severe", "color": "climate_arctic", "always_winter": true, "colonial_migration_size_modifier": -0.3, "debug_color": "rgb"}

## topography

Definitions: `flatland`, `mountains`, `hills`, `plateau`, `wetlands`, `ocean`, `deep_ocean`, `coastal_ocean`, `inland_sea`, `narrows`, `lakes`, `high_lakes`, `salt_pans`, `atoll`, `flatland_wasteland`, `hills_wasteland`, `plateau_wasteland`, `wetlands_wasteland`, `dune_wasteland`, `mesa_wasteland`, `mountain_wasteland`, `ocean_wasteland`.

Scalar configuration fields (complete, including presentation and movement settings):

- `flatland`: {"color": "terrain_grasslands", "movement_cost": 1.0, "vegetation_density": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `mountains`: {"color": "terrain_mountain", "movement_cost": 2, "proximity": -0.5, "defender": 2, "vegetation_density": 0.2, "blocked_in_winter": true, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "colonial_migration_size_modifier": -0.2, "debug_color": "rgb"}

- `hills`: {"color": "terrain_hills", "defender": 1, "vegetation_density": 0.6, "movement_cost": 1.5, "proximity": -0.25, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "colonial_migration_size_modifier": -0.1, "debug_color": "rgb"}

- `plateau`: {"color": "terrain_plateau", "defender": 1, "vegetation_density": 0.8, "movement_cost": 1.25, "proximity": -0.125, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `wetlands`: {"color": "terrain_marsh", "movement_cost": 1.5, "proximity": -0.25, "defender": 1, "vegetation_density": 0.6, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "colonial_migration_size_modifier": -0.1, "debug_color": "rgb"}

- `ocean`: {"color": "terrain_ocean", "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "hsv360"}

- `deep_ocean`: {"color": "terrain_deep_ocean", "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "is_deep_ocean": true, "debug_color": "hsv360"}

- `coastal_ocean`: {"color": "terrain_coastal_ocean", "can_have_ice": true, "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "hsv360"}

- `inland_sea`: {"color": "terrain_inland_sea", "can_freeze_over": true, "can_have_ice": true, "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "hsv360"}

- `narrows`: {"color": "terrain_narrows", "can_freeze_over": true, "can_have_ice": true, "movement_cost": 1.2, "defender": 1, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "hsv360"}

- `lakes`: {"color": "terrain_lakes", "can_freeze_over": true, "can_have_ice": true, "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "is_lake": true, "debug_color": "hsv360"}

- `high_lakes`: {"color": "terrain_high_lakes", "can_freeze_over": true, "can_have_ice": true, "movement_cost": 1.0, "is_lake": true, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "hsv360"}

- `salt_pans`: {"color": "terrain_salt_pans", "can_freeze_over": false, "movement_cost": 1.0, "is_lake": true, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `atoll`: {"color": "terrain_atoll", "can_freeze_over": false, "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "hsv360"}

- `flatland_wasteland`: {"color": "terrain_grasslands", "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `hills_wasteland`: {"color": "terrain_hills_wasteland", "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `plateau_wasteland`: {"color": "terrain_rock_wasteland", "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `wetlands_wasteland`: {"color": "terrain_marsh_wasteland", "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `dune_wasteland`: {"color": "terrain_dune_wasteland", "movement_cost": 1.0, "vegetation_density": -1, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "has_sand": true, "debug_color": "rgb"}

- `mesa_wasteland`: {"color": "terrain_mesa_wasteland", "movement_cost": 1.0, "vegetation_density": -1, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `mountain_wasteland`: {"color": "terrain_mountain_wasteland", "movement_cost": 1.0, "blocked_in_winter": true, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

- `ocean_wasteland`: {"color": "terrain_ocean_wasteland", "movement_cost": 1.0, "weather_front_strength_change_percent": 0, "weather_cyclone_strength_change_percent": 0, "weather_tornado_strength_change_percent": 0, "debug_color": "rgb"}

## vegetation

Definitions: `desert`, `sparse`, `grasslands`, `farmland`, `woods`, `forest`, `jungle`.

Scalar configuration fields (complete, including presentation and movement settings):

- `desert`: {"color": "terrain_desert", "movement_cost": 1.1, "proximity": -0.05, "has_sand": true, "colonial_migration_size_modifier": -0.2, "debug_color": "rgb"}

- `sparse`: {"color": "terrain_steppe", "movement_cost": 1.0, "colonial_migration_size_modifier": -0.1, "debug_color": "rgb"}

- `grasslands`: {"color": "terrain_grasslands", "movement_cost": 1.0, "debug_color": "rgb"}

- `farmland`: {"color": "terrain_farmlands", "movement_cost": 1.1, "proximity": -0.05, "colonial_migration_size_modifier": 0.1, "debug_color": "rgb"}

- `woods`: {"color": "terrain_woods", "movement_cost": 1.25, "proximity": -0.125, "defender": 1, "debug_color": "rgb"}

- `forest`: {"color": "terrain_forest", "movement_cost": 1.5, "proximity": -0.25, "defender": 1, "colonial_migration_size_modifier": -0.1, "debug_color": "rgb"}

- `jungle`: {"color": "terrain_jungle", "movement_cost": 2, "proximity": -0.5, "defender": 1, "colonial_migration_size_modifier": -0.3, "debug_color": "rgb"}

## Map classifications

`provinces`, `rivers`, `topology`, `adjacencies`, `setup`, `ports`, `location_templates`, `equator_y`, `wrap_x`, `sound_toll`, `volcanoes`, `earthquakes`, `sea_zones`, `lakes`, `impassable_mountains`, `non_ownable`

## Native geography GUI

Verified in in_game/gui/location_window.gui, lines 4150–4510: topography, climate, vegetation, coastal/inland, ice blockade, harbour suitability, river, sound toll, volcano, HasWinter, earthquakes.

## Winter correction

The native GUI really does call Location.HasWinter (location_window.gui:4480). The exported scripting trigger list does not contain a trigger named has_winter. It exposes location_max_winter_level, winter_level and winter_power. Climate definitions specify winter = none/mild/normal/severe. Thus these interfaces exist, but they must not be described as unrelated, independently assigned template fields.

The imported inventory has has_winter, climate_winter and maximum_winter_magnitude. Across all 20,929 populated climate rows, has_winter equals climate_winter != none, and maximum_winter_magnitude equals climate_winter. These cached columns are redundant descriptions of the climate setting, not measurements of current game weather.

## Relevant native script interfaces

### climate
Checks if a location is of a specific climate
Reads gamestate for all scopes.
**Supported Scopes**: location

### has_earthquakes
Check if a location has a Earthquakes
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### has_river
Check if a location has a river
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### has_volcano
Check if a location has a volcano
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### is_adjacent_to_lake
Check if a location is a adjacent to a lake
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### is_coastal
Check if a location is coastal
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### is_land
Check if a location is land
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### is_ownable
Check if a location is ownable, i.e. not sea, lake or an impassable
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### is_passable
Check if a location is passable
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### is_port
Check if a location has a port
Traits: yes/no 
Reads gamestate for all scopes.
**Supported Scopes**: location

### location_max_winter_level
Checks the maximum winter level of a location
Reads gamestate for all scopes.
**Supported Scopes**: location

### location_size
Checks if a location has a certain pixel count
Traits: <, <=, =, !=, >, >=
Reads gamestate for all scopes.
**Supported Scopes**: location

### topography
Checks if a location is of a specific Topography type
Reads gamestate for all scopes.
**Supported Scopes**: location

### vegetation
Checks if a location is of a specific Vegetation type
Reads gamestate for all scopes.
**Supported Scopes**: location

### winter_level
winter level check
Reads gamestate for all scopes.
**Supported Scopes**: location

### winter_power
Traits: <, <=, =, !=, >, >=
Reads gamestate for all scopes.
**Supported Scopes**: location

## Interpretation

The template movement_assistance field contains coordinate pairs; it is map configuration, not a scalar agricultural workability attribute. modifier attaches a named static modifier. Neither is an additional natural-quality category. Culture and religion are also present in the template, but describe society. Location rank and other economic/political state are additional dynamic context; this is a geographical-property audit, not an enumeration of all game-state queries.

The proposal adds soil type, accessible freshwater supply, river regime and natural drainage. It removes no existing property. Extending climate/topography/vegetation values must retain their existing engine settings.

## Source fingerprints

- `/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/map_data/location_templates.txt`: SHA256 `cffefb6fd02eb8ff5ced9a8a9f1ce5dab5084d82de790c29acf7413e3354ab91`

- `/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/map_data/default.map`: SHA256 `69530759cc2c511983109f144deeb31e6b1e583aa76488cd500fcc2e3c731499`

- `/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/common/climates/00_default.txt`: SHA256 `0c9e02a85eec7d8bf10eea64183c9c0c5561f1eb08012114ed8c08c998e19b54`

- `/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/common/topography/00_default.txt`: SHA256 `bc3321e5d9d56f3ab1d4f6a08653e1624de2787e1265a2eb4dcd8639be78bfa0`

- `/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/common/vegetation/00_default.txt`: SHA256 `b4d4c4b0f19741426b8b147fee1f92db35e0c4f969c7cd6c50959c056c075eb9`

- `/mnt/c/Games/steamapps/common/Europa Universalis V/game/in_game/gui/location_window.gui`: SHA256 `4147ffa27d1a40429127fbc5a75175965225e215b1ca1cad48f141ef94016e2c`

- `/mnt/c/Users/Anwender/Documents/Paradox Interactive/Europa Universalis V/docs/triggers.log`: SHA256 `60743f6b72c98b8fb807a56acf6e7343eb415b319e312d55cb14d5dabfd64f06`
