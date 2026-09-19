"""Compare the saved World Builder river baseline with the no-overshoot rerun."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from historical_agriculture.attribute_fit import ROOT, metrics
from historical_agriculture.soil_types import sha


def main():
    before = ROOT / "artifacts/attribute_fit"
    after = ROOT / "artifacts/attribute_fit_no_overshoot"
    a = pd.read_csv(before / "location_predictions.csv", keep_default_na=False).set_index("location_tag")
    b = pd.read_csv(after / "location_predictions.csv", keep_default_na=False).set_index("location_tag")
    assert a.index.equals(b.index) and len(b) == 20893
    ra = json.loads((before / "report.json").read_text())
    rb = json.loads((after / "report.json").read_text())
    for key, value in ra["inputs"].items():
        if key.startswith(("artifacts/", "data/")):
            assert rb["inputs"][key] == value == sha(ROOT / key), key
    for key, value in ra["config"].items():
        if key != "notes":
            assert rb["config"][key] == value, key
    fields = ["base_effective_cropland", "capacity_multiplier", "starting_improvement_effective_cropland", "maximum_improvement_effective_cropland", *ra["config"]["features"], "validation_fold"]
    pd.testing.assert_frame_equal(a[fields], b[fields])
    assert b.starting_improvement_effective_cropland.ge(0).all()
    assert b.maximum_improvement_effective_cropland.ge(0).all()
    rows = []
    for mode in ["fitted", "heldout"]:
        for label, improvement in [("Base land", None), ("Multiplier", None), ("Base × multiplier", 0), ("Starting capacity", "starting_improvement_effective_cropland"), ("Maximum capacity", "maximum_improvement_effective_cropland")]:
            for version, frame in [("previous", a), ("no_overshoot", b)]:
                base = frame[f"current_base_effective_cropland_absolute_{mode}"].to_numpy()
                multiplier = frame[f"current_capacity_multiplier_absolute_{mode}"].to_numpy()
                if label == "Base land":
                    truth, predicted, tolerance = frame.base_effective_cropland.to_numpy(), base, .005
                elif label == "Multiplier":
                    truth, predicted, tolerance = frame.capacity_multiplier.to_numpy(), multiplier, 1e-7
                else:
                    addition = 0 if improvement == 0 else frame[improvement].to_numpy()
                    truth = (frame.base_effective_cropland.to_numpy() + addition) * frame.capacity_multiplier.to_numpy()
                    predicted = (base + addition) * multiplier
                    tolerance = .005 * frame.capacity_multiplier.to_numpy() + 1e-7 * (frame.base_effective_cropland.to_numpy() + addition + .005)
                error = predicted / truth - 1
                overshoots = int(np.sum(predicted > truth + tolerance))
                if version == "no_overshoot" and mode == "fitted":
                    assert overshoots == 0, (label, overshoots)
                rows.append({"target": label, "evaluation": mode, "version": version, **metrics(truth, predicted), "overshoots_above_tolerance": overshoots, "under_by_more_than_20_percent": int(np.sum(error < -.2)), "under_by_more_than_50_percent": int(np.sum(error < -.5)), "total_target": float(truth.sum()), "total_predicted": float(predicted.sum()), "total_shortfall_percent": float(100 * (1 - predicted.sum() / truth.sum()))})
    result = pd.DataFrame(rows)
    result.to_csv(after / "before_after_metrics.csv", index=False)
    base = b.current_base_effective_cropland_absolute_fitted
    multiplier = b.current_capacity_multiplier_absolute_fitted
    truth = b.base_effective_cropland * b.capacity_multiplier
    prediction = base * multiplier
    regional = b[["region", "macro_region"]].assign(target=truth, predicted=prediction, shortfall=truth - prediction, shortfall_percent=100*(1-prediction/truth))
    regions = regional.groupby(["macro_region", "region"]).agg(locations=("target", "size"), target=("target", "sum"), predicted=("predicted", "sum"), shortfall=("shortfall", "sum"), median_shortfall_percent=("shortfall_percent", "median"))
    regions["total_shortfall_percent"] = 100 * (1 - regions.predicted / regions.target)
    regions.sort_values("shortfall", ascending=False).to_csv(after / "capacity_shortfall_by_region.csv")
    worst = b.assign(inert_target=truth, inert_prediction=prediction, inert_shortfall=truth-prediction, inert_shortfall_percent=100*(1-prediction/truth))
    worst.sort_values("inert_shortfall", ascending=False).to_csv(after / "capacity_shortfall_by_location.csv", index_label="location_tag")
    lines = ["# No-overshoot fit with the new rivers", "", "Recomputed all 20,893 ownable locations. Targets, river levels, other attributes, coefficient bounds, loss weights and region folds match the previous saved fit. Input hashes and row-by-row values were checked. The original map is preserved.", "", "Hard constraints apply separately to base land and multiplier at every training location. This is stricter than bounding only their product. Predictions remain shared additive coefficients; there is no location-specific clipping. Existing global prediction bounds remain in force, including for unseen attribute combinations.", "", "## Full-map result", "", "| Target | Previous median error | No-overshoot median shortfall | Locations >50% too low | Previous R² | No-overshoot R² |", "|---|---:|---:|---:|---:|---:|"]
    for target in result.target.unique():
        previous = result[(result.target == target) & (result.evaluation == "fitted") & (result.version == "previous")].iloc[0]
        current = result[(result.target == target) & (result.evaluation == "fitted") & (result.version == "no_overshoot")].iloc[0]
        lines.append(f"| {target} | {previous.median_absolute_percentage_error:.2f}% | {current.median_absolute_percentage_error:.2f}% | {current.under_by_more_than_50_percent:,} | {previous.r2:.4f} | {current.r2:.4f} |")
    floor_locations = b[b.capacity_multiplier.eq(.25)]
    category_coverage = {feature: set(b[feature].astype(str)) == set(floor_locations[feature].astype(str)) for feature in ra["config"]["features"]}
    assert all(category_coverage.values())
    (after / "floor_constraint_audit.json").write_text(json.dumps({"multiplier_floor_locations": len(floor_locations), "all_categories_observed_at_floor": category_coverage}, indent=2)+"\n")
    lines += ["", f"Multiplier range: {multiplier.min():.10f}–{multiplier.max():.10f}. All {int(np.isclose(multiplier,.25,rtol=0,atol=1e-7).sum()):,} locations are at the 0.25 floor within numerical tolerance. There are {len(floor_locations):,} target-floor locations, collectively containing every category of every predictor. Since the existing global lower bound also applies to every possible attribute combination, each category appearing at a floor-target location must have its minimum effect. All categories are covered, forcing all centered effects to zero and the intercept to 0.25. This collapse is mathematically required by the combined constraints.", "", "Zero full-map overshoots above solver tolerance: 0.005 base units and 0.0000001 multiplier, with propagated tolerance for derived capacities. Tiny floating-point differences are retained in the data; predictions are never clipped. Starting and maximum capacities retain the same actual improvement quantities.", "", "## Largest regional shortfalls in base × multiplier", "", "Ranked by total lost capacity, not by percentage. Location counts and relative error are included so large regions do not look intrinsically less accurate merely because of their size.", "", "| Region | Locations | Total shortfall | Share of target missing | Median location shortfall |", "|---|---:|---:|---:|---:|"]
    for (macro, region), row in regions.sort_values("shortfall", ascending=False).head(12).iterrows():
        lines.append(f"| {region} | {int(row.locations):,} | {row.shortfall:,.0f} | {row.total_shortfall_percent:.2f}% | {row.median_shortfall_percent:.2f}% |")
    lines += ["", "## Held-out validation", "", "Entire regions remain outside both the fitting objective and ceiling constraints. Overshoot is possible here; constraining these targets would leak validation information. Use the map’s evaluation selector to inspect those failures separately.", "", "| Target | Previous R² | No-overshoot R² | Held-out locations overshooting |", "|---|---:|---:|---:|"]
    for target in result.target.unique():
        previous = result[(result.target == target) & (result.evaluation == "heldout") & (result.version == "previous")].iloc[0]
        current = result[(result.target == target) & (result.evaluation == "heldout") & (result.version == "no_overshoot")].iloc[0]
        lines.append(f"| {target} | {previous.r2:.4f} | {current.r2:.4f} | {current.overshoots_above_tolerance:,} |")
    lines += ["", "Reproduce: `uv run worldbuilder attribute-fit --config configs/attribute_fit_no_overshoot.json`, then `uv run python tools/compare_no_overshoot_fit.py`.", "", "[New interactive map](index.html) · [Previous map](../attribute_fit/index.html) · [Exact comparison](before_after_metrics.csv) · [Regional shortfalls](capacity_shortfall_by_region.csv) · [Location shortfalls](capacity_shortfall_by_location.csv)", "", "![Previous and no-overshoot maps](comparison.png)"]
    (after / "comparison.md").write_text("\n".join(lines) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from PIL import Image
    fig, axes = plt.subplots(2, 1, figsize=(16, 16), facecolor="#0c1420")
    for ax, folder, title in zip(axes, [before, after], ["Previous fit · new rivers", "No-overshoot fit · same rivers and targets"]):
        ax.imshow(Image.open(folder / "fitted_2.png"))
        ax.set_title(title, color="white", fontsize=18, pad=12)
        ax.axis("off")
    fig.subplots_adjust(left=.02,right=.98,top=.96,bottom=.08,hspace=.1)
    cmap = LinearSegmentedColormap.from_list("error", ["#2a6fbb", "#e7eae7", "#bf353a"])
    cax = fig.add_axes([.2,.04,.6,.013])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(-100,100),cmap=cmap),cax=cax,orientation="horizontal",ticks=[-100,-50,0,50,100])
    cb.ax.tick_params(colors="white");cb.set_label("Base × multiplier error (%) · full-map fit · improvements excluded",color="white")
    fig.savefig(after / "comparison.png", dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(result[result.version.eq("no_overshoot")][["target","evaluation","r2","median_absolute_percentage_error","overshoots_above_tolerance","under_by_more_than_50_percent"]].to_string(index=False))
    print(regions.sort_values("shortfall", ascending=False).head(8).to_string())


if __name__ == "__main__":
    main()
