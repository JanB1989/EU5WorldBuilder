"""Normalize generated fertility artwork using the soil asset pipeline."""
from pathlib import Path
from prepare_soil_icons import prepare
from preview_fertility_icons import render

if __name__=='__main__':
    prepare(Path(__file__).resolve().parents[1]/'assets/geography_test/fertility')
    render()
