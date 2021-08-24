# DensPart performs Atoms-in-molecules density partitioning.
# Copyright (C) 2011-2020 The DensPart Development Team
#
# This file is part of DensPart.
#
# DensPart is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# DensPart is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>
# --
"""Generic code for variational Hirshfeld methods.

This code is very preliminary, so no serious docstrings yet.
"""


from functools import partial
import time

import numpy as np
from scipy.optimize import minimize


__all__ = ["optimize_pro_model", "BasisFunction", "ProModel", "ekld"]


def optimize_pro_model(pro_model, grid, density, gtol=1e-8, density_cutoff=1e-10):
    """Optimize the promodel using the trust-constr minimizer from SciPy.

    Parameters
    ----------
    pro_model
        The model for the pro-molecular density, an instance of ``ProModel``.
        It contains the initial parameters as an attribute.
    grid
        The integration grid, an instance of ``grid.basegrid.Grid``.
    density
        The electron density evaluated on the grid.
    gtol
        Convergence parameter gtol of SciPy's trust-constr minimizer.
    density_cutoff
        Density cutoff used to estimated sizes of local grids. Set to zero for
        whole-grid integrations. (This will not work for periodic systems.)

    Returns
    -------
    pro_model
        The model for the pro-molecular density, an instance of ``ProModel``.
        It contains the optimized parameters as an attribute.
    localgrids
        Local integration grids used for the pro-model basis functions.

    """
    # Precompute the local grids.
    print("Building local grids")
    localgrids = [
        grid.get_localgrid(fn.center, fn.get_cutoff_radius(density_cutoff))
        for fn in pro_model.fns
    ]
    # Compute the total population
    pop = np.einsum("i,i", grid.weights, density)
    print("Integral of density:", pop)
    # Define initial guess and cost
    print("Optimization")
    print("#Iter         elkd          kld   constraint     grad.rms  cputime (s)")
    print("-----  -----------  -----------  -----------  -----------  -----------")
    pars0 = np.concatenate([fn.pars for fn in pro_model.fns])
    cost_grad = partial(
        ekld,
        grid=grid,
        density=density,
        pro_model=pro_model,
        localgrids=localgrids,
        pop=pop,
    )
    with np.errstate(all="raise"):
        # The errstate is changed to detect potentially nasty numerical issues.
        # Optimize parameters within the bounds.
        bounds = sum([fn.bounds for fn in pro_model.fns], [])

        optresult = minimize(
            cost_grad,
            pars0,
            method="trust-constr",
            jac=True,
            hess="2-point",
            bounds=bounds,
            options={"gtol": gtol},
        )

    print("-----  -----------  -----------  -----------  -----------  -----------")
    # Check for convergence.
    print('Optimizer message: "{}"'.format(optresult.message))
    if not optresult.success:
        raise RuntimeError("Convergence failure.")
    # Wrap up
    print("Total charge:       {:20.7e}".format(pro_model.atnums.sum() - pop))
    print("Sum atomic charges: {:20.7e}".format(pro_model.charges.sum()))
    pro_model.assign_pars(optresult.x)
    return pro_model, localgrids


class BasisFunction:
    """Base class for atom-centered basis functions for the pro-molecular density.

    Each basis function instance stores also its parameters in ``self.pars``,
    which are always kept up-to-date. This simplifies the code a lot because
    the methods below can easily access the ``self.pars`` attribute when they
    need it, instead of having to rely on the caller to pass them in correctly.
    This is in fact a typical antipattern, but here it works well.
    """

    def __init__(self, iatom, center, pars, bounds):
        """Initialize a basis function.

        Parameters
        ----------
        iatom
            Index of the atom with which this function is associated.
        center
            The center of the function in Cartesian coordinates.
        pars
            The initial values of the proparameters for this function.
        bounds
            List of tuples with ``(lower, upper)`` bounds for each parameter.
            Use ``-np.inf`` and ``np.inf`` to disable bounds.

        """
        if len(pars) != len(bounds):
            raise ValueError(
                "The number of parameters must equal the number of bounds."
            )
        self.iatom = iatom
        self.center = center
        self.pars = pars
        self.bounds = bounds

    @property
    def npar(self):  # noqa: D401
        """Number of parameters."""
        return len(self.pars)

    @property
    def population(self):  # noqa: D401
        """Population of this basis function."""
        raise NotImplementedError

    @property
    def population_derivatives(self):  # noqa: D401
        """Derivatives of the population w.r.t. proparameters."""
        raise NotImplementedError

    def get_cutoff_radius(self, density_cutoff):
        """Estimate the cutoff radius for the given density cutoff."""
        raise NotImplementedError

    def compute(self, points):
        """Compute the basisfunction values on a grid."""
        raise NotImplementedError

    def compute_derivatives(self, points):
        """Compute derivatives of the basisfunction values on a grid."""
        raise NotImplementedError


class ProModel:
    """Base class for the promolecular density."""

    def __init__(self, atnums, atcoords, fns):
        """Initialize the prodensity model.

        Parameters
        ----------
        atnums
            Atomic numbers
        atcoords
            Atomic coordinates
        fns
            A list of basis functions, instances of ``BasisFunction``.
        """
        self.atnums = atnums
        self.atcoords = atcoords
        self.fns = fns
        self.ncompute = 0

    @property
    def natom(self):  # noqa: D401
        """Number of atoms."""
        return len(self.atnums)

    @property
    def charges(self):  # noqa: D401
        """Proatomic charges."""
        charges = np.array(self.atnums, dtype=float)
        for fn in self.fns:
            charges[fn.iatom] -= fn.population
        return charges

    def get_results(self):
        """Return dictionary with additional results derived from the pro-parameters."""
        # Number of functions per atom
        atnfn = np.zeros(self.natom, dtype=int)
        atnpar = np.zeros(self.natom, dtype=int)
        for fn in self.fns:
            atnfn[fn.iatom] += 1
            atnpar[fn.iatom] += len(fn.pars)
        return {
            "atnfn": atnfn,
            "atnpar": atnpar,
            "propars": np.concatenate([fn.pars for fn in self.fns]),
        }

    @property  # noqa: D401
    def population(self):
        """Promolecular population."""
        return sum(fn.population for fn in self.fns)

    def assign_pars(self, pars):
        """Assign the promolecule parameters to the basis functions."""
        ipar = 0
        for fn in self.fns:
            fn.pars[:] = pars[ipar : ipar + fn.npar]
            ipar += fn.npar

    def compute_density(self, grid, localgrids):
        """Compute prodensity on a grid (for the given parameters).

        Parameters
        ----------
        grid
            The whole integration grid, on which the results is computed.
        localgrids
            A list of local grids, one for each basis function.

        Returns
        -------
        pro
            The prodensity on the points of ``grid``.

        """
        self.ncompute += 1
        pro = np.zeros_like(grid.weights)
        for fn, localgrid in zip(self.fns, localgrids):
            np.add.at(pro, localgrid.indices, fn.compute(localgrid.points))
        return pro

    def compute_proatom(self, iatom, grid):
        """Compute proatom density on a grid (for the given parameters).

        Parameters
        ----------
        iatom
            The atomic index.
        grid
            The whole integration grid, on which the results is computed.

        Returns
        -------
        pro
            The prodensity on the points of ``grid``.

        """
        pro = np.zeros_like(grid.weights)
        for fn in self.fns:
            if fn.iatom == iatom:
                pro += fn.compute(grid.points)
        return pro

    def pprint(self):
        """Print a table with the pro-parameters."""
        print(" ifn iatom  atn       parameters...")
        for ifn, fn in enumerate(self.fns):
            print(
                "{:4d}  {:4d}  {:3d}  {:s}".format(
                    ifn,
                    fn.iatom,
                    self.atnums[fn.iatom],
                    " ".join(format(par, "15.8f") for par in fn.pars),
                )
            )


def ekld(pars, grid, density, pro_model, localgrids, pop, density_cutoff=1e-15):
    """Compute the Extended KL divergence and its gradient.

    Parameters
    ----------
    pars
        A NumPy array with promodel parameters.
    grid
        A numerical integration grid with, instance of ``grid.basegrid.Grid``.
    density
        The electron density evaluated on the grid.
    pro_model
        The model for the pro-molecular density, an instance of ``ProModel``.
    local_grids
        A list of local integration grids for the pro-model basis functions.
    pop
        The integral of density, to be precomputed before calling this function.
    density_cutoff
        Density cutoff used to neglect grid points with low densities. Including
        them can result in numerical noise in the result and its derivatives.

    Returns
    -------
    ekld
        The extended KL-d, i.e. including the Lagrange multiplier.
    gradient
        The gradient of ekld w.r.t. the pro-model parameters.

    """
    time_start = time.process_time()

    pro_model.assign_pars(pars)
    pro = pro_model.compute_density(grid, localgrids)

    # Compute potentially tricky quantities.
    sick = (density < density_cutoff) | (pro < density_cutoff)
    with np.errstate(all="ignore"):
        lnratio = np.log(density) - np.log(pro)
        ratio = density / pro
    lnratio[sick] = 0.0
    ratio[sick] = 0.0
    # Function value
    kld = np.einsum("i,i,i", grid.weights, density, lnratio)

    constraint = pop - pro_model.population
    result = kld - constraint
    # Gradient
    ipar = 0
    gradient = np.zeros_like(pars)

    for ifn, fn in enumerate(pro_model.fns):
        localgrid = localgrids[ifn]
        fn_derivatives = fn.compute_derivatives(localgrid.points)
        gradient[ipar : ipar + fn.npar] = fn.population_derivatives - np.einsum(
            "i,i,ji", localgrid.weights, ratio[localgrid.indices], fn_derivatives
        )
        ipar += fn.npar

    # Screen output
    time_stop = time.process_time()
    print(
        "{:5d} {:12.7f} {:12.7f} {:12.4e} {:12.4e} {:12.7f}".format(
            pro_model.ncompute,
            result,
            kld,
            -constraint,
            # TODO: projected gradient may be better.
            np.linalg.norm(gradient) / np.sqrt(len(gradient)),
            time_stop - time_start,
        )
    )
    return result, gradient
