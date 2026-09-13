# Equal-area base-land floor and pressure review

The active equal-area dataset applies a minimum of 1,000 base effective-land units to every ownable location. This is a user-selected game allowance, explicitly separate from physical land evidence. The multiplier and all improvement quantities remain unchanged. Added base units times the multiplier are added to inert, starting and maximum capacity. Remaining opportunity is preserved.

4,921 ownable locations gain a total of 4,500,074.82 capacity. Equal-area ownable starting capacity increases from 753.548 to 758.048 million. Over-capacity locations fall from 9,143 to 7,520 of 20,893; over-capacity provinces fall from 1,451 to 1,172 of 3,819.

Of the remaining 7,520 over-capacity locations, 1,990 are inside provinces with enough aggregate starting capacity. This is a potential food-sharing explanation, not proof of actual food production or distribution. Of 1,172 over-capacity provinces, 752 fall within their modeled maximum; 420 exceed it. Provincial classification uses the sum of ownable locations and contextual starting population, with no population used to determine model values.

Priorities: inspect extreme geographical/assignment failures in western India, the Indus/Punjab area, selected Chinese provinces and the Andes. Investigate dated crop availability, water service, terrain aggregation, cultivated extent and management assumptions before changing shared productivity. Test inherited improvements where documented and within credible opportunity budgets. Explicitly diagnose urban supply dependence rather than demanding each city be locally self-sufficient. Do not increase all regions or fit each location to population. Equal-area scaling is an intentional game abstraction and should be part of diagnostics where local totals diverge.

Examples after the floor: Hangzhou province has 1.258m population and 2.717m support; Suzhou 2.784m and 3.248m; Wenzhou 0.951m and 0.090m; Cairo province 1.142m and 0.296m. Egypt overall has 5.076m population versus 3.425m starting and 3.503m current modeled maximum, so shifting remaining irrigation alone cannot close that discrepancy. Maximum currently expands clearing/irrigation at fixed crop and management, not every possible future technology.

The minimum is not a guarantee of subsistence equilibrium: 1,000 effective units produce 250 to 5,000 base capacity at the allowed multiplier bounds. It does not imply literal hectares.

Reproduce with `uv run ha1300 locations`, `uv run python scripts/validate_locations.py`, and `uv run pytest -q`. Per-province/region review tables are generated local files `data/processed/base_floor_province_pressure.csv` and `data/processed/base_floor_region_pressure.csv`. The pre-floor comparison is archived locally under `data/processed/base_floor_before`. All four location values remain complete; no game export or deployment.
