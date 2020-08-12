#!/usr/bin/env python3

import argparse

import numpy as np

from grid.basegrid import Grid

from denspart.mbis import partition
from denspart.properties import compute_rcubed


def main():
    """Partitioning command-line interface."""
    args = parse_args()
    data = np.load(args.fn_rho)
    if data["cellvecs"].size == 0:
        grid = Grid(data["points"], data["weights"])
    else:
        raise NotImplementedError
    rho = data["rho"]
    print("Sanity checks")
    print("Integral of rho:", grid.integrate(rho))
    print("MBIS partitioning")
    pro_model = partition(data["atnums"], data["atcoords"], grid, rho)
    print("Properties")
    results = {
        "charges": pro_model.charges,
        "rcubed": compute_rcubed(pro_model, grid, rho),
    }
    print("Charges:")
    print(results["charges"])
    print("Total charge:", pro_model.charges.sum())
    print("R^3 moments:")
    print(results["rcubed"])
    np.savez(args.fn_results, **results)


def parse_args():
    """Parse command-line arguments."""
    DESCRIPTION = """\
    Density partitioning of a given density on a grid.
    """
    parser = argparse.ArgumentParser(prog="denspart", description=DESCRIPTION)
    parser.add_argument("fn_rho", help="The NPZ file with grid and density.")
    parser.add_argument(
        "fn_results", help="The NPZ file in which resutls will be stored."
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
