# Food-system and people-per-hectare revision

The [main page](../artifacts/reconstruction/index.html) now contains the food-system map, lower/upper/estimated historical people-per-used-hectare maps, and the Seshat graph in matching food-energy units. Diagnostics are collapsed.

All 3259820 GAEZ land cells have a conditional classification. 3243564 have numeric values; 16256 remain unquantified. These are visible and not filled with zeros. There are 32 passing tests, and every comparable Seshat anchor remains enclosed (21 inside, 2 unresolved).

Non-crop numbers remain experimental. FORGE supplies present-day environmental model outputs; livestock uses a provisional standing-biomass/stocking transfer with FAO product coefficients. This is not a validated global 1300 livestock model. Aquatic food remains excluded from terrestrial hectare values. See the [method](food_system_method.md) and [numerical basis](../artifacts/reconstruction/food_validation.json).

No cell area or cultivated-area quantity is used. The shared food requirement is 2,500 kcal/day. Historical/current maps represent food-energy equivalents, not observed population.

Reproduce: `uv run ha1300 acquire`, `uv run ha1300 run`, `uv run pytest -q --junitxml=reports/tests.xml`.

Source/configuration/code fingerprint: `7bc4f06ad7530a9edf2c75c58dd55a990f75415d3f8d9fc822e09f4755c22c33`.
