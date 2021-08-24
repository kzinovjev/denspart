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
"""Compute atom-in-molecules properties."""


import numpy as np


__all__ = ["compute_radial_moments"]


def compute_radial_moments(pro_model, grid, density, localgrids, nmax=4):
    """Compute expectation values of r^n for each atom.

    Parameters
    ----------
    pro_model
        The model for the pro-molecular density, an instance of ``ProModel``.
    grid
        The whole integration grid, instance of ``grid.basegrid.Grid.``
    density
        The electron density.
    localgrids
        A list of local grids, one for each basis function.
    nmax
        Maximum degree of the radial moment to be computed.

    Returns
    -------
    rexp
        An array with expectation values of r^n for n from 0 to nmax.

    """
    pro = pro_model.compute_density(grid, localgrids)
    result = np.zeros((pro_model.natom, nmax + 1))
    for iatom, atcoord in enumerate(pro_model.atcoords):
        # TODO: improve cutoff
        localgrid = grid.get_localgrid(atcoord, 8.0)
        dists = np.linalg.norm(localgrid.points - atcoord, axis=1)
        pro_atom = pro_model.compute_proatom(iatom, localgrid)
        ratio = pro_atom / pro[localgrid.indices]
        for degree in np.arange(nmax + 1):
            result[iatom, degree] = localgrid.integrate(
                density[localgrid.indices], dists ** degree, ratio
            )
    return result
