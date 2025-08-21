#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from common.params import Params

# 各品牌 CAR 的 import 路径
BRANDS = {
    "hyundai": "opendbc.car.hyundai.values",
    "gm": "opendbc.car.gm.values",
    "toyota": "opendbc.car.toyota.values",
    "mazda": "opendbc.car.mazda.values",
    "tesla": "opendbc.car.tesla.values",
    "honda": "opendbc.car.honda.values",
    "volkswagen": "opendbc.car.volkswagen.values",
}

PARAMS_PATH = Params().get_param_path()

def write_supported_cars(brand: str, module_path: str, outfile: str):
    try:
        mod = __import__(module_path, fromlist=["CAR"])
        car_list = sorted([c for c in dir(mod.CAR) if not c.startswith("__")])
        filepath = os.path.join(PARAMS_PATH, outfile)
        with open(filepath, "w") as f:
            f.write("\n".join(car_list))
        print(f"[✓] {brand} -> {filepath}")
    except Exception as e:
        print(f"[!] Failed for {brand}: {e}")

def main():
    for brand, module_path in BRANDS.items():
        outfile = "SupportedCars" if brand == "hyundai" else f"SupportedCars_{brand}"
        write_supported_cars(brand, module_path, outfile)

if __name__ == "__main__":
    main()
