"""
Module for calculating the historic portfolio volatility for a given strategy.
"""

from typing import List, Optional, Callable, Tuple
import pandas as pd
import numpy as np
from macrosynergy.panel.historic_vol import expo_std, flat_std, expo_weights
from macrosynergy.management.types import NoneType, QuantamentalDataFrame
from macrosynergy.management.utils import (
    reduce_df,
    standardise_dataframe,
    is_valid_iso_date,
    qdf_to_ticker_df,
    ticker_df_to_qdf,
    get_eops,
    get_cid,
)

RETURN_SERIES_XCAT = "_PNL_USD1S_ASD"


def _univariate_volatility(
    df_wide: pd.DataFrame,
    roll_func: Callable,
    lback_periods: int,
    nan_tolerance: float,
    remove_zeros: bool,
    weights: Optional[np.ndarray],
):
    """
    Calculates the univariate volatility for a given dataframe.

    :param <pd.DataFrame> df_wide: the wide dataframe of all the tickers in the strategy.
    :param <callable> roll_func: the function to use for the rolling window calculation.
        The function must have a signature of (np.ndarray, *, remove_zeros: bool) -> float.
        See `expo_std` and `flat_std` for examples.
    :param <bool> remove_zeros: removes zeroes as invalid entries and shortens the
        effective window.
    :param <np.ndarray> weights: array of exponential weights for each period in the
        lookback window. Default is None, which means that the weights are equal.
    """
    if weights is None:
        weights = np.ones(df_wide.shape[0]) / df_wide.shape[0]
        univariate_vol: pd.Series = df_wide.agg(roll_func, remove_zeros=remove_zeros)
    else:
        if len(weights) == len(df_wide):
            univariate_vol = df_wide.agg(
                roll_func, w=weights, remove_zeros=remove_zeros
            )
        else:
            return pd.Series(np.nan, index=df_wide.columns)

        ## Creating a mask to fill series `nan_tolerance`
    mask = (
        (
            df_wide.isna().sum(axis=0)
            + (df_wide == 0).sum(axis=0)
            + (lback_periods - len(df_wide))
        )
        / lback_periods
    ) <= nan_tolerance

    univariate_vol[~mask] = np.nan

    return univariate_vol


def _estimate_variance_covariance(pivot: pd.DataFrame) -> pd.DataFrame:
    # TODO add complexity of weighting and estimation methods
    vcv = pivot.cov()
    return vcv


def _hist_vol(
    pivot_signals: pd.DataFrame,
    pivot_returns: pd.DataFrame,
    sname: str,
    rstring: str,
    est_freq: str = "m",
    lback_periods: int = 21,
    lback_meth: str = "ma",
    half_life=11,
    nan_tolerance: float = 0.25,
    remove_zeros: bool = True,
):
    """
    Calculates historic volatility for a given strategy. It assumes that the dataframe
    is composed solely of the relevant signals and returns for the strategy.

    :param <pd.DataFrame> pivot_signals: the pivot table of the contract signals.
    :param <pd.DataFrame> pivot_returns: the pivot table of the contract returns.
    :param <str> est_freq: the frequency of the volatility estimation. Default is 'm'
        for monthly. Alternatives are 'w' for business weekly, 'd' for daily, and 'q'
        for quarterly. Estimations are conducted for the end of the period.
    :param <int> lback_periods: the number of periods to use for the lookback period
        of the volatility-targeting method. Default is 21.
    :param <str> lback_meth: the method to use for the lookback period of the
        volatility-targeting method. Default is 'ma' for moving average. Alternative is
        "xma", for exponential moving average.
    :param <int> half_life: Refers to the half-time for "xma" and full lookback period
        for "ma". Default is 11.
    :param <float> nan_tolerance: maximum ratio of NaNs to non-NaNs in a lookback window,
        if exceeded the resulting volatility is set to NaN. Default is 0.25.
    :param <bool> remove_zeros: removes zeroes as invalid entries and shortens the
        effective window.
    """

    # TODO split into steps:
    # [1] Find rebalance dates.
    # [2] Calculate variance-covariance matrix for each rebalance date.
    # [3] Calculate variance of portfolio for each rebalance date weighted by signal.

    lback_meth = lback_meth.lower()
    if lback_meth not in ["ma", "xma"]:
        raise NotImplementedError(
            f"`lback_meth` must be 'ma' or 'xma'; got {lback_meth}"
        )

    # df_wide: pd.DataFrame = qdf_to_ticker_df(df=df)
    # df_wide = df_wide[sorted(df_wide.columns)]  # Sort columns to keep debugging easier

    # NOTE: `get_eops` helps identify the dates for which the volatility calculation
    # will be performed. This is done by identifying the last date of each cycle.
    # We use `get_eops` primarily because it has a clear and defined behaviour for all frequencies.
    # It was originally designed as part of the `historic_vol` module, but it is
    # used here as well.

    trigger_indices = get_eops(
        dates=pivot_signals.index,
        freq=est_freq,
    )

    
    # dfw_calc: pd.DataFrame = pd.DataFrame(
    #     index=trigger_indices, columns=[return_series], dtype=float
    # )

    # expo_weights_arr: Optional[np.ndarray] = None
    # if lback_meth == "xma":
    #     expo_weights_arr: np.ndarray = expo_weights(
    #         lback_periods=lback_periods,
    #         half_life=half_life,
    #     )

    # _args: dict = dict(remove_zeros=remove_zeros, rstring=rstring, sname=sname)

    # if est_freq == "d":
    #     if lback_meth == "xma":
    #         _args.update(dict(func=expo_std, w=expo_weights_arr))
    #     elif lback_meth == "ma":
    #         _args.update(dict(func=flat_std))

    # else:
    #     _args.update(
    #         dict(
    #             lback_periods=lback_periods,
    #             nan_tolerance=nan_tolerance,
    #         )
    #     )
    #     if lback_meth == "xma":
    #         _args.update(dict(roll_func=expo_std, w=expo_weights_arr))
    #     elif lback_meth == "ma":
    #         _args.update(dict(roll_func=flat_std))

    # if est_freq == "d":
    #     # dfw_calc = df_wide.rolling(lback_periods).agg(**_args)
    #     raise NotImplementedError("Daily volatility not implemented yet.")
    #     # TODO: Contradiction to other condition above

    # else:
    #     for r_date in trigger_indices:
    #         dfw_calc.loc[r_date, :] = _rolling_window_calc(
    #             real_date_pdt=r_date,
    #             ticker_df=df_wide,
    #             **_args,
    #         )

    # fills = {"d": 1, "w": 5, "m": 24, "q": 64}
    # dfw_calc = dfw_calc.reindex(df_wide.index).ffill(limit=fills[est_freq])


    # TODO get the correct rebalance dates
    # TODO allow for multiple estimation frequency
    list_vcv: List[Tuple[pd.Timestamp, pd.DataFrame, pd.Series]] = [
        (trigger_date, _estimate_variance_covariance(pivot=pivot_returns.loc[pivot_returns.index <= trigger_date].iloc[-lback_periods:]), pivot_signals.loc[trigger_date, :])
        for trigger_date in trigger_indices
    ]

    list_pvol = [(tt, signal.T.dot(vcv).dot(signal)) for tt, vcv, signal in list_vcv]
    portfolio_return_name = f"{sname}{RETURN_SERIES_XCAT}"
    df_out = pd.DataFrame(list_pvol, columns=["real_date", portfolio_return_name]).set_index("real_date")

    # Annualised standard deviation (ASD)
    df_out[portfolio_return_name] = np.sqrt(df_out[portfolio_return_name]) * np.sqrt(252)

    return ticker_df_to_qdf(df=df_out)


def historic_portfolio_vol(
    df: pd.DataFrame,
    sname: str,
    fids: List[str],
    est_freq: str = "m",
    lback_periods: int = 21,
    lback_meth: str = "ma",
    half_life=11,
    rstring: str = "XR",
    start: Optional[str] = None,
    end: Optional[str] = None,
    blacklist: Optional[dict] = None,
    nan_tolerance: float = 0.25,
    remove_zeros: bool = True,
):
    """
    Estimates annualized standard deviations of a portfolio, based on historic
    variances and co-variances.

    :param <pd.DataFrame> df:  standardized JPMaQS DataFrame with the necessary
        columns: 'cid', 'xcat', 'real_date' and 'value'.
        This dataframe must contain contract-specific signals and return series.
    :param <str> sname: the name of the strategy. It must correspond to contract
        signals in the dataframe, which have the format "<cid>_<ctype>_CSIG_<sname>", and
        which are typically calculated by the function contract_signals().
    :param <List[str]> fids: list of financial contract identifiers in the format
        "<cid>_<ctype>". It must correspond to contract signals in the dataframe.
    :param <str> est_freq: the frequency of the volatility estimation. Default is 'm'
        for monthly. Alternatives are 'w' for business weekly, 'd' for daily, and 'q'
        for quarterly. Estimations are conducted for the end of the period.
    :param <int> lback_periods: the number of periods to use for the lookback period
        of the volatility-targeting method. Default is 21.
    :param <str> lback_meth: the method to use for the lookback period of the
        volatility-targeting method. Default is 'ma' for moving average. Alternative is
        "xma", for exponential moving average.
    :param <str> rstring: a general string of the return category. This identifies
        the contract returns that are required for the volatility-targeting method, based
        on the category identifier format <cid>_<ctype><rstring> in accordance with
        JPMaQS conventions. Default is 'XR'.
    :param <str> start: the start date of the data. Default is None, which means that
        the start date is taken from the dataframe.
    :param <str> end: the end date of the data. Default is None, which means that
        the end date is taken from the dataframe.
    :param <dict> blacklist: a dictionary of contract identifiers to exclude from
        the calculation. Default is None, which means that no contracts are excluded.
    :param <float> nan_tolerance: maximum ratio of NaNs to non-NaNs in a lookback window,
        if exceeded the resulting volatility is set to NaN. Default is 0.25.
    :param <bool> remove_zeros: if True (default) any returns that are exact zeros will
        not be included in the lookback window and prior non-zero values are added to the
        window instead.


    :return: <pd.DataFrame> JPMaQS dataframe of annualized standard deviation of
        estimated strategy PnL, with category name <sname>_PNL_USD1S_ASD.
        TODO: check if this is correct.
        The values are in % annualized. Values between estimation points are forward
        filled.

    N.B.: If returns in the lookback window are not available the function will replace
    them with the average of the available returns of the same contract type. If no
    returns are available for a contract type the function will reduce the lookback window
    up to a minimum of 11 days. If no returns are available for a contract type for
    at least 11 days the function returns an NaN for that date and sends a warning of all
    the dates for which this happened.


    """
    ## Check inputs
    for varx, namex, typex in [
        (df, "df", pd.DataFrame),
        (sname, "sname", str),
        (fids, "fids", list),
        (est_freq, "est_freq", str),
        (lback_periods, "lback_periods", int),
        (lback_meth, "lback_meth", str),
        (half_life, "half_life", int),
        (rstring, "rstring", str),
        (start, "start", (str, NoneType)),
        (end, "end", (str, NoneType)),
        (blacklist, "blacklist", (dict, NoneType)),
    ]:
        if not isinstance(varx, typex):
            raise ValueError(f"`{namex}` must be {typex}.")
        if typex in [str, list, dict] and len(varx) == 0:
            raise ValueError(f"`{namex}` must not be an empty {str(typex)}.")

    ## Standardize and copy DF
    df: pd.DataFrame = standardise_dataframe(df.copy())

    ## Check the dates
    if start is None:
        start: str = pd.Timestamp(df["real_date"].min()).strftime("%Y-%m-%d")
    if end is None:
        end: str = pd.Timestamp(df["real_date"].max()).strftime("%Y-%m-%d")

    for dx, nx in [(start, "start"), (end, "end")]:
        if not is_valid_iso_date(dx):
            raise ValueError(f"`{nx}` must be a valid ISO-8601 date string")

    ## Reduce the dataframe
    df: pd.DataFrame = reduce_df(df=df, start=start, end=end, blacklist=blacklist)

    ## Check the strategy name
    if not isinstance(sname, str):
        raise ValueError("`sname` must be a string.")

    df["ticker"] = df["cid"] + "_" + df["xcat"]

    ## Check that there is atleast one contract signal for the strategy
    if not any(df["ticker"].str.endswith(f"_CSIG_{sname}")):
        raise ValueError(f"No contract signals for strategy `{sname}`.")

    u_tickers: List[str] = list(df["ticker"].unique())
    for contx in fids:
        if not any(
            [tx.startswith(contx) and tx.endswith(f"_CSIG_{sname}") for tx in u_tickers]
        ):
            raise ValueError(f"Contract identifier `{contx}` not in dataframe.")

    if not all([f"{contx}{rstring}" in u_tickers for contx in fids]):
        missing_tickers = [
            f"{contx}_{rstring}"
            for contx in fids
            if f"{contx}_{rstring}" not in u_tickers
        ]
        raise ValueError(
            f"The dataframe is missing the following return series: {missing_tickers}"
        )

    ## Filter DF and select CSIGs and XR
    filt_csigs: List[str] = [tx for tx in u_tickers if tx.endswith(f"_CSIG_{sname}")]

    filt_xrs: List[str] = [
        tx for tx in u_tickers if tx.endswith(f"{rstring}")
    ]

    # df: pd.DataFrame = df.loc[df["ticker"].isin(filt_csigs + filt_xrs)]
    df["fid"] = df["cid"] + "_" + df["xcat"].str.split("_").map(lambda x: x[0][:-2] if x[0].endswith("XR") else x[0])
    pivot_signals: pd.DataFrame = df.loc[df.ticker.isin(filt_csigs)].pivot(index="real_date", columns="fid", values="value")
    pivot_returns: pd.DataFrame = df.loc[df.ticker.isin(filt_xrs)].pivot(index="real_date", columns="fid", values="value")
    assert set(pivot_signals.columns) == set(pivot_returns.columns)

    # TODO the same?
    assert all(pivot_signals.columns == pivot_returns.columns)

    hist_port_vol: pd.DataFrame = _hist_vol(
        pivot_returns=pivot_returns,
        pivot_signals=pivot_signals,
        sname=sname,
        rstring=rstring,
        est_freq=est_freq,
        lback_periods=lback_periods,
        lback_meth=lback_meth,
        half_life=half_life,
        nan_tolerance=nan_tolerance,
        remove_zeros=remove_zeros,
    )

    assert isinstance(hist_port_vol, QuantamentalDataFrame)

    return hist_port_vol


if __name__ == "__main__":
    from macrosynergy.management.simulate import make_test_df
    from contract_signals import contract_signals

    cids: List[str] = ["EUR", "GBP", "AUD", "CAD"]
    xcats: List[str] = ["SIG", "HR"]

    start: str = "2000-01-01"
    end: str = "2020-12-31"

    df: pd.DataFrame = make_test_df(
        cids=cids,
        xcats=xcats,
        start=start,
        end=end,
    )

    df.loc[(df["cid"] == "USD") & (df["xcat"] == "SIG"), "value"] = 1.0
    ctypes = ["FX", "EQ"]
    cscales = [1.0, 0.5]
    csigns = [1, -1]

    hbasket = ["GBP_FX", "EUR_FX"]
    hscales = [0.7, 0.3]

    df_cs: pd.DataFrame = contract_signals(
        df=df,
        sig="SIG",
        cids=cids,
        ctypes=ctypes,
        cscales=cscales,
        csigns=csigns,
        hbasket=hbasket,
        hscales=hscales,
        hratios="HR",
        sname="mySTRAT",
    )

    ## `df_cs` looks like:
    #       real_date  cid              xcat         value
    # 0     2000-01-03  AUD  EQ_CSIG_mySTRAT     -0.009126
    # 1     2000-01-03  AUD  FX_CSIG_mySTRAT      0.018252
    # 2     2000-01-03  CAD  EQ_CSIG_mySTRAT    -25.028669
    # 3     2000-01-03  CAD  FX_CSIG_mySTRAT     50.057339
    # 4     2000-01-03  EUR  EQ_CSIG_mySTRAT    -50.000000
    # ...          ...  ...              ...           ...
    # 43827 2020-12-31  CAD  FX_CSIG_mySTRAT     50.000000
    # 43828 2020-12-31  EUR  EQ_CSIG_mySTRAT    -49.926954
    # 43829 2020-12-31  EUR  FX_CSIG_mySTRAT   9088.903408
    # 43830 2020-12-31  GBP  EQ_CSIG_mySTRAT    -25.000000
    # 43831 2020-12-31  GBP  FX_CSIG_mySTRAT  21024.448833

    df_xr = make_test_df(
        cids=cids,
        xcats=["EQXR", "FXXR"],
        start=start,
        end=end,
    )
    #   TODO returns need to be daily percent changes, and sensible values...
    ## `df_xr` looks like:
    #         real_date  cid xcat       value
    # 0     2000-01-03  EUR  EQXR  100.000000
    # 1     2000-01-04  EUR  EQXR   99.853908
    # 2     2000-01-05  EUR  EQXR   99.707816
    # 3     2000-01-06  EUR  EQXR   99.561724
    # 4     2000-01-07  EUR  EQXR   99.415632
    # ...          ...  ...  ...         ...
    # 43827 2020-12-25  CAD  FXXR   99.269540
    # 43828 2020-12-28  CAD  FXXR   99.415632
    # 43829 2020-12-29  CAD  FXXR   99.561724
    # 43830 2020-12-30  CAD  FXXR   99.707816
    # 43831 2020-12-31  CAD  FXXR   99.853908

    ...

    ## Concatenate the dataframes
    dfX = pd.concat([df_cs, df_xr], axis=0)

    fids: List[str] = [f"{cid}_{ctype}" for cid in cids for ctype in ctypes]
    # fids = ['EUR_FXXR', 'EUR_EQXR', 'GBP_FXXR', 'GBP_EQXR', 'AUD_FXXR', 'AUD_EQXR', 'CAD_FXXR', 'CAD_EQXR']

    
    df_vol: pd.DataFrame = historic_portfolio_vol(
        df=dfX,
        sname="mySTRAT",
        fids=fids,
        est_freq="m",
        lback_periods=15,
        lback_meth="ma",
        half_life=11,
        rstring="XR",
        start=start,
        end=end,
    )

    ## `df_vol` looks like:
    #       real_date      cid           xcat         value
    # 0    2000-01-31  mySTRAT  PNL_USD1S_ASD    519.638295
    # 1    2000-02-01  mySTRAT  PNL_USD1S_ASD    519.638295
    # 2    2000-02-02  mySTRAT  PNL_USD1S_ASD    519.638295
    # 3    2000-02-03  mySTRAT  PNL_USD1S_ASD    519.638295
    # 4    2000-02-04  mySTRAT  PNL_USD1S_ASD    519.638295
    # ...         ...      ...            ...           ...
    # 5454 2020-12-25  mySTRAT  PNL_USD1S_ASD  80932.561430
    # 5455 2020-12-28  mySTRAT  PNL_USD1S_ASD  80932.561430
    # 5456 2020-12-29  mySTRAT  PNL_USD1S_ASD  80932.561430
    # 5457 2020-12-30  mySTRAT  PNL_USD1S_ASD  80932.561430
    # 5458 2020-12-31  mySTRAT  PNL_USD1S_ASD  79138.839677
