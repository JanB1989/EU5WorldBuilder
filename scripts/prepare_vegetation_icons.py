"""Reproduce keyed native vegetation icons from retained generated originals."""
from pathlib import Path
from prepare_soil_icons import prepare
if __name__=='__main__':
    prepare(Path(__file__).resolve().parents[1]/'assets/geography_test/vegetation')
