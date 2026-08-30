# Kerr/QNM research workflows

## Before interpreting a numerical result

Record or locate the repository's choices for units and mass normalization; Fourier and time-dependence sign; spin weight and angular-mode conventions; radial coordinate and tortoise-coordinate branches; horizon and infinity boundary conditions; overtone indexing; and the sign used for damped complex frequencies. A numerically stable answer can still be incompatible with a comparison source when one of these conventions differs.

Treat mode tracking as a continuity problem when parameters vary. Near crossings, exceptional behavior, or nearly degenerate roots, compare eigenfunctions, separation constants, residuals, and continuation history rather than sorting frequencies alone.

## Numerical checks

Use more than solver convergence for consequential results. Useful independent checks include:

- residual evaluation at higher precision than the solve;
- precision or tolerance sweeps with stable reported digits;
- agreement between distinct radial or angular formulations when available;
- boundary-condition and Wronskian diagnostics;
- continuation from a trusted parameter point;
- symmetry or limiting-case checks, including the nonrotating limit where applicable;
- comparison against a cited benchmark with its conventions translated explicitly.

Do not silently replace the project's precision type with binary floating point. Preserve complex branch choices and type promotion across Julia/Python boundaries.

## Reproducibility record

For a result that will be kept, capture the Git commit and dirty state, Julia and Python versions, package manifests or lockfiles, platform, input parameters, precision and tolerances, random seeds if any, command arguments, and output hashes. Keep raw outputs separate from derived plots or tables.

The bundled toolchain is one reproducible Linux profile, not a claim that every project must use those exact versions. Use project manifests and CI matrices to test supported versions.

## Execution scope

Workspace inspection, source review, unit tests, protocol probes, and short numerical canaries are appropriate defaults. A broad scan or long-running production solve needs an explicit objective, bounded parameter region, resource plan, checkpoint strategy, and user authorization.
