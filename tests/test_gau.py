import numpy as np
import pytest
from numpy import linalg
import numpy.testing as npt
import itertools
from utils import get_rstate, get_printing
import matplotlib

matplotlib.use('Agg')
from matplotlib import pyplot as plt  # noqa
import dynesty  # noqa
from dynesty import plotting as dyplot  # noqa
from dynesty import utils as dyfunc  # noqa
"""
Run a series of basic tests to check whether anything huge is broken.

"""

nlive = 500
printing = get_printing()


def bootstrap_tol(results, rstate):
    """ Compute the uncertainty of means/covs by doing bootstrapping """
    n = len(results.logz)
    niter = 50
    pos = results.samples
    wts = np.exp(results.logwt - results.logz[-1])
    means = []
    covs = []

    for i in range(niter):
        # curpos = dyfunc.resample_equal(pos, wts)
        # xid = np.random.randint(len(curpos), size=len(curpos))
        sub = rstate.uniform(size=n) < wts / wts.max()
        ind0 = np.nonzero(sub)[0]
        ind1 = rstate.choice(ind0, size=len(ind0), replace=True)
        mean = pos[ind1].mean(axis=0)
        cov = np.cov(pos[ind1].T)
        means.append(mean)
        covs.append(cov)
    return np.std(means, axis=0), np.std(covs, axis=0)


def check_results(results,
                  mean_truth,
                  cov_truth,
                  logz_truth,
                  mean_tol,
                  cov_tol,
                  logz_tol,
                  sig=5):
    """ Check if means and covariances match match expectations
    within the tolerances

    """
    pos = results.samples
    wts = np.exp(results.logwt - results.logz[-1])
    mean, cov = dyfunc.mean_and_cov(pos, wts)
    logz = results.logz[-1]
    npt.assert_array_less(np.abs(mean - mean_truth), sig * mean_tol)
    npt.assert_array_less(np.abs(cov - cov_truth), sig * cov_tol)
    npt.assert_array_less(np.abs((logz_truth - logz)), sig * logz_tol)


# GAUSSIAN TEST


class Gaussian:
    def __init__(self, corr=.95):
        self.ndim = 3
        self.mean = np.linspace(-1, 1, self.ndim)
        self.cov = np.identity(self.ndim)  # set covariance to identity matrix
        self.cov[self.cov ==
                 0] = corr  # set off-diagonal terms (strongly correlated)
        self.cov_inv = linalg.inv(self.cov)  # precision matrix
        self.lnorm = -0.5 * (np.log(2 * np.pi) * self.ndim +
                             np.log(linalg.det(self.cov)))
        self.prior_win = 10  # +/- 10 on both sides
        self.logz_truth = self.ndim * (-np.log(2 * self.prior_win))

    # 3-D correlated multivariate normal log-likelihood
    def loglikelihood(self, x):
        """Multivariate normal log-likelihood."""
        return -0.5 * np.dot(
            (x - self.mean), np.dot(self.cov_inv,
                                    (x - self.mean))) + self.lnorm

    # prior transform
    def prior_transform(self, u):
        """Flat prior between -10. and 10."""
        return self.prior_win * (2. * u - 1.)

    # gradient (no jacobian)
    def grad_x(self, x):
        """Multivariate normal log-likelihood gradient."""
        return -np.dot(self.cov_inv, (x - self.mean))

    # gradient (with jacobian)
    def grad_u(self, x):
        """Multivariate normal log-likelihood gradient."""
        return -np.dot(self.cov_inv, x - self.mean) * 2 * self.prior_win


def check_results_gau(results, g, rstate, sig=5, logz_tol=None):
    if logz_tol is None:
        logz_tol = sig * results.logzerr[-1]
    mean_tol, cov_tol = bootstrap_tol(results, rstate)
    check_results(results,
                  g.mean,
                  g.cov,
                  g.logz_truth,
                  mean_tol,
                  cov_tol,
                  logz_tol,
                  sig=sig)


def test_gaussian():
    sig = 5
    rstate = get_rstate()
    g = Gaussian()
    sampler = dynesty.NestedSampler(g.loglikelihood,
                                    g.prior_transform,
                                    g.ndim,
                                    nlive=nlive,
                                    rstate=rstate)
    sampler.run_nested(print_progress=printing)
    # check that jitter/resample/simulate_run work
    # for not dynamic sampler
    dyfunc.jitter_run(sampler.results, rstate=rstate)
    dyfunc.resample_run(sampler.results, rstate=rstate)
    dyfunc.simulate_run(sampler.results, rstate=rstate)

    # add samples
    # check continuation behavior
    sampler.run_nested(dlogz=0.1, print_progress=printing)

    # get errors
    nerr = 3
    result_list = []
    for i in range(nerr):
        sampler.reset()
        sampler.run_nested(print_progress=False)
        results = sampler.results
        result_list.append(results)
        pos = results.samples
        wts = np.exp(results.logwt - results.logz[-1])
        mean, cov = dyfunc.mean_and_cov(pos, wts)
        logz = results.logz[-1]
        assert (np.abs(logz - g.logz_truth) < sig * results.logzerr[-1])
    res_comb = dyfunc.merge_runs(result_list)
    assert (np.abs(res_comb.logz[-1] - g.logz_truth) <
            sig * results.logzerr[-1])
    # check summary
    res = sampler.results
    res.summary()

    # check plots
    dyplot.runplot(sampler.results)
    plt.close()
    dyplot.traceplot(sampler.results)
    plt.close()
    dyplot.cornerpoints(sampler.results)
    plt.close()
    dyplot.cornerplot(sampler.results)
    plt.close()
    dyplot.boundplot(sampler.results,
                     dims=(0, 1),
                     it=3000,
                     prior_transform=g.prior_transform,
                     show_live=True,
                     span=[(-10, 10), (-10, 10)])
    plt.close()
    dyplot.cornerbound(sampler.results,
                       it=3500,
                       prior_transform=g.prior_transform,
                       show_live=True,
                       span=[(-10, 10), (-10, 10)])
    plt.close()


# try all combinations excepte none/unif
@pytest.mark.parametrize(
    "bound,sample",
    list(
        itertools.product(['single', 'multi', 'balls', 'cubes'],
                          ['unif', 'rwalk', 'slice', 'rslice'])) +
    list(itertools.product(['none'], ['rwalk', 'slice', 'rslice'])))
def test_bounding_sample(bound, sample):
    # check various bounding methods

    rstate = get_rstate()
    if bound == 'none':
        g = Gaussian(0.1)
        # make live easy if bound is none
    else:
        g = Gaussian()
    sampler = dynesty.NestedSampler(g.loglikelihood,
                                    g.prior_transform,
                                    g.ndim,
                                    nlive=nlive,
                                    bound=bound,
                                    sample=sample,
                                    rstate=rstate)
    sampler.run_nested(print_progress=printing)
    check_results_gau(sampler.results, g, rstate)


@pytest.mark.parametrize("bound,sample",
                         itertools.product(
                             ['single', 'multi', 'balls', 'cubes'], ['unif']))
def test_bounding_bootstrap(bound, sample):
    # check various bounding methods

    rstate = get_rstate()
    g = Gaussian()
    sampler = dynesty.NestedSampler(g.loglikelihood,
                                    g.prior_transform,
                                    g.ndim,
                                    nlive=nlive,
                                    bound=bound,
                                    sample=sample,
                                    bootstrap=5,
                                    rstate=rstate)
    sampler.run_nested(print_progress=printing)
    check_results_gau(sampler.results, g, rstate)


# extra checks for gradients
def test_slice_nograd():
    rstate = get_rstate()
    g = Gaussian()
    sampler = dynesty.NestedSampler(g.loglikelihood,
                                    g.prior_transform,
                                    g.ndim,
                                    nlive=nlive,
                                    sample='hslice',
                                    rstate=rstate)
    sampler.run_nested(print_progress=printing)
    check_results_gau(sampler.results, g, rstate)


def test_slice_grad():
    rstate = get_rstate()
    g = Gaussian()
    sampler = dynesty.NestedSampler(g.loglikelihood,
                                    g.prior_transform,
                                    g.ndim,
                                    nlive=nlive,
                                    sample='hslice',
                                    gradient=g.grad_x,
                                    compute_jac=True,
                                    rstate=rstate)
    sampler.run_nested(print_progress=printing)
    check_results_gau(sampler.results, g, rstate)


def test_slice_grad1():
    rstate = get_rstate()
    g = Gaussian()
    sampler = dynesty.NestedSampler(g.loglikelihood,
                                    g.prior_transform,
                                    g.ndim,
                                    nlive=nlive,
                                    sample='hslice',
                                    gradient=g.grad_u,
                                    rstate=rstate)
    sampler.run_nested(print_progress=printing)
    check_results_gau(sampler.results, g, rstate)


def test_dynamic():
    # check dynamic nested sampling behavior
    rstate = get_rstate()
    g = Gaussian()
    dsampler = dynesty.DynamicNestedSampler(g.loglikelihood,
                                            g.prior_transform,
                                            g.ndim,
                                            rstate=rstate)
    dsampler.run_nested(print_progress=printing)
    check_results_gau(dsampler.results, g, rstate)

    # check error analysis functions
    dres = dyfunc.jitter_run(dsampler.results, rstate=rstate)
    check_results_gau(dres, g, rstate)
    dres = dyfunc.resample_run(dsampler.results, rstate=rstate)
    check_results_gau(dres, g, rstate)
    dres = dyfunc.simulate_run(dsampler.results, rstate=rstate)
    check_results_gau(dres, g, rstate)

    dyfunc.kld_error(dsampler.results, rstate=rstate)
