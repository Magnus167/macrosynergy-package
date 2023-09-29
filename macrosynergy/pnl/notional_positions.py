"""
Module for calculating notional positions based on contract signals, assets-under-management, 
and other relevant parameters.

::docs::notional_positions::sort_first::
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from typing import List, Union, Tuple, Optional

from macrosynergy.management.simulate_quantamental_data import make_qdf, make_test_df
from macrosynergy.management.shape_dfs import reduce_df
from macrosynergy.management.utils import standardise_dataframe, is_valid_iso_date
from macrosynergy.panel import historic_vol
from macrosynergy.pnl import Numeric, NoneType, _short_xcat


def _apply_slip(
    target_df: pd.DataFrame,
    slip: int,
    cids: List[str],
    xcats: List[str],
    metrics: List[str],
) -> pd.DataFrame:
    """
    Applied a slip, i.e. a negative lag, to the target DataFrame
    for the given cross-sections and categories, on the given metrics.

    :param <pd.DataFrame> target_df: DataFrame to which the slip is applied.
    :param <int> slip: Slip to be applied.
    :param <List[str]> cids: List of cross-sections.
    :param <List[str]> xcats: List of categories.
    :param <List[str]> metrics: List of metrics to which the slip is applied.
    :return <pd.DataFrame> target_df: DataFrame with the slip applied.
    :raises <TypeError>: If the provided parameters are not of the expected type.
    :raises <ValueError>: If the provided parameters are semantically incorrect.
    """

    target_df = target_df.copy()
    if not (isinstance(slip, int) and slip >= 0):
        raise ValueError("Slip must be a non-negative integer.")

    sel_tickers: List[str] = [f"{cid}_{xcat}" for cid in cids for xcat in xcats]
    target_df["tickers"] = target_df["cid"] + "_" + target_df["xcat"]

    if not set(sel_tickers).issubset(set(target_df["tickers"].unique())):
        raise ValueError(
            "Tickers targetted for applying slip are not present in the DataFrame.\n"
            f"Missing tickers: {set(sel_tickers) - set(target_df['tickers'].unique())}"
        )

    slip: int = slip.__neg__()

    target_df[metrics] = target_df.groupby("tickers")[metrics].shift(slip)
    target_df = target_df.drop(columns=["tickers"])

    return target_df


def notional_positions(
    df: pd.DataFrame,
    sname: str,
    contids: List[str],
    aum: Numeric = 100,
    dollar_per_signal: Numeric = 1.0,
    leverage: Optional[Numeric] = None,
    vol_target: Optional[Numeric] = None,
    rebal_freq: str = "m",
    slip: int = 1,
    lback_periods: int = 21,
    lback_meth: str = "ma",
    half_life=11,
    rstring: str = "XR",
    start: Optional[str] = None,
    end: Optional[str] = None,
    blacklist: Optional[dict] = None,
    pname: str = "POS",
):
    """
    Calculates contract positions based on contract signals, AUM and other specs.

    :param <pd.DataFrame> df:  standardized JPMaQS DataFrame with the necessary
        columns: 'cid', 'xcat', 'real_date' and 'value'.
        This dataframe must contain the contract-specific signals and possibly
        related return series (for vol-targeting).
    :param <str> sname: the name of the strategy. It must correspond to contract
        signals in the dataframe, which have the format "<cid>_<ctype>_<sname>_CSIG", and
        which are typically calculated by the function contract_signals().
    :param <List[str]> contids: list of contract identifiers in the format
        "<cid>_<ctype>". It must correspond to contract signals in the dataframe.
    :param <float> aum: the assets under management in USD million (for consistency).
        This is basis for all position sizes. Default is 100.
    :param <float> dollar_per_signal: the amount of notional currency (e.g. USD) per
        contract signal value. Default is 1. The default scale has no specific meaning
        and is merely a basis for tryouts.
    :param <float> leverage: the ratio of the sum of notional positions to AUM.
        This is the main basis for leveraged-based positioning. Since different
        contracts have different expected volatility and correlations this method
        does not control expected volatility. Default is None, i.e. the method is not
        applied.
    :param <float> vol_target: the target volatility of the portfolio in % of AUM.
        This is the main parameter for volatility-targeted positioning. That method
        estimates the annualized standard deviation of the signal-based portfolio
        for a 1 USD per signal portfolio based on past variances and covariances of
        the contract returns. The estimation is managed by the function
        `historic_portfolio_vol()`.
        Default is None, i.e. the volatility-targeting is not applied.
    :param <str> rebal_freq: the rebalancing frequency. Default is 'm' for monthly.
        Alternatives are 'w' for business weekly, 'd' for daily, and 'q' for quarterly.
        Contract signals are taken from the end of the holding period and applied to
        positions at the beginning of the next period, subject to slippage.
    :param <int> slip: the number of days to wait before applying the signal. Default is 1.
        This means that positions are taken at the very end of the first business day
        of the holding period.
    :param <int> lback_periods: the number of periods to use for the lookback period
        of the volatility-targeting method. Default is 21. This passed through to
        the function `historic_portfolio_vol()`.
    :param <str> lback_meth: the method to use for the lookback period of the
        volatility-targeting method. Default is 'ma' for moving average. Alternative is
        "xma", for exponential moving average. Again this is passed through to
        the function `historic_portfolio_vol()`.
    :param <int> half_life: the half-life of the exponential moving average for the
        volatility-targeting method. Default is 11. This is passed through to
        the function `historic_portfolio_vol()`.
    :param <str> rstring: a general string of the return category. This identifies
        the contract returns that are required for the volatility-targeting method, based
        on the category identifier format <cid>_<ctype><rstring>_<rstring> in accordance
        with JPMaQS conventions. Default is 'XR'.
    :param <str> start: the start date of the data. Default is None, which means that
        the start date is taken from the dataframe.
    :param <str> end: the end date of the data. Default is None, which means that
        the end date is taken from the dataframe.
    :param <dict> blacklist: a dictionary of contract identifiers to exclude from
        the calculation. Default is None, which means that no contracts are excluded.
    :param <str> pname: the name of the position. Default is 'POS'.

    :return: <pd.DataFrame> with the positions for all traded contracts and the
        specified strategy in USD million. It has the standard JPMaQS DataFrame.
        The contract signals have the following format "<cid>_<ctype>_<sname>_<pname>".

    """
    for varx, namex, typex in [
        (df, "df", pd.DataFrame),
        (sname, "sname", str),
        (contids, "contids", list),
        (aum, "aum", Numeric),
        (dollar_per_signal, "dollar_per_signal", Numeric),
        (leverage, "leverage", (Numeric, NoneType)),
        (vol_target, "vol_target", (Numeric, NoneType)),
        (rebal_freq, "rebal_freq", str),
        (slip, "slip", int),
        (lback_periods, "lback_periods", int),
        (lback_meth, "lback_meth", str),
        (half_life, "half_life", int),
        (rstring, "rstring", str),
        (start, "start", (str, NoneType)),
        (end, "end", (str, NoneType)),
        (blacklist, "blacklist", (dict, NoneType)),
        (pname, "pname", str),
    ]:
        if not isinstance(varx, typex):
            raise ValueError(f"`{namex}` must be {typex}.")

        if isinstance(varx, (str, list, dict)) and len(varx) == 0:
            raise ValueError(f"`{namex}` must not be an empty {str(typex)}.")

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

    ## Check the contract identifiers and contract signals

    df["tickers"]: str = df["cid"] + "_" + df["xcat"]

    # there must be atleast one contract signal with the strategy name
    if not any(df["tickers"].str.endswith(f"_{sname}_CSIG")):
        raise ValueError(f"No contract signals for strategy `{sname}` in dataframe.")


def historic_portfolio_vol(
    df: pd.DataFrame,
    sname: str,
    contids: List[str],
    est_freq: str = "m",
    lback_periods: int = 21,
    lback_meth: str = "ma",
    half_life=11,
    rstring: str = "XR",
    start: Optional[str] = None,
    end: Optional[str] = None,
    blacklist: Optional[dict] = None,
):
    """
    Estimates the annualized standard deviations of a changing portfolio of contracts.

    :param <pd.DataFrame> df:  standardized JPMaQS DataFrame with the necessary
        columns: 'cid', 'xcat', 'real_date' and 'value'.
        This dataframe must contain the contract-specific signals and return series.
    :param <str> sname: the name of the strategy. It must correspond to contract
        signals in the dataframe, which have the format "<cid>_<ctype>_<sname>_CSIG", and
        which are typically calculated by the function contract_signals().
    :param <list[str]> contids: list of contract identifiers in the format
        "<cid>_<ctype>". It must correspond to contract signals in the dataframe.
    :param <str> est_freq: the frequency of the volatility estimation. Default is 'm'
        for monthly. Alternatives are 'w' for business weekly, 'd' for daily, and 'q'
        for quarterly. Estimations are conducted for the end of the period.
    :param <float> dollar_per_signal: the amount of notional currency (e.g. USD) per
        contract signal value. Default is 1. The default scale has no specific meaning
        and is merely a basis for tryouts.
    :param <int> lback_periods: the number of periods to use for the lookback period
        of the volatility-targeting method. Default is 21. This passed through to
        the function `historic_portfolio_vol()`.
    :param <str> lback_meth: the method to use for the lookback period of the
        volatility-targeting method. Default is 'ma' for moving average. Alternative is
        "xma", for exponential moving average. Again this is passed through to
        the function `historic_portfolio_vol()`.
    :param <str> rstring: a general string of the return category. This identifies
        the contract returns that are required for the volatility-targeting method, based
        on the category identifier format <cid>_<ctype><rstring>_<rstring> in accordance
        with JPMaQS conventions. Default is 'XR'.
    :param <str> start: the start date of the data. Default is None, which means that
        the start date is taken from the dataframe.
    :param <str> end: the end date of the data. Default is None, which means that
        the end date is taken from the dataframe.
    :param <dict> blacklist: a dictionary of contract identifiers to exclude from
        the calculation. Default is None, which means that no contracts are excluded.


    :return: <pd.DataFrame> with the annualized standard deviations of the portfolios.
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
        # (sname, "sname", str),
        (contids, "contids", list),
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

    ## Add ticker column and filter for snames
    df["tickers"]: str = df["cid"] + "_" + df["xcat"]
    df: pd.DataFrame = df.loc[df["tickers"].str.endswith(f"_{sname}_CSIG")]

    df["scat"] = df.apply(lambda x: _short_xcat(xcat=x["xcat"]), axis=1)
    df["contid"] = df["cid"] + "_" + df["scat"]

    ## Check the contract identifiers
    u_contids: List[str] = list(df["contid"].unique())
    if not all([cid in u_contids for cid in contids]):
        raise ValueError(
            f"Contract identifiers must be in the dataframe. "
            f"Missing: {set(contids) - set(u_contids)}"
        )

    ## Run calcs using historic_vol()

    expanded_conts: List[Tuple[str, str]] = [contx.split("_", 1) for contx in contids]

    calc_dfs: List[pd.DataFrame] = []

    for contx in expanded_conts:
        cid, ctype = contx
        cdf: pd.DataFrame = df.loc[(df["cid"] == cid) & (df["scat"] == ctype)].copy()

        # drop xcat, rename scat to xcat
        cdf = cdf.drop(columns=["xcat", "contid"]).rename(columns={"scat": "xcat"})

        cdf = historic_vol(
            df=cdf,
            xcat=ctype,
            est_freq=est_freq,
            lback_periods=lback_periods,
            lback_meth=lback_meth,
            half_life=half_life,
            postfix=rstring,
        )

        calc_dfs.append(cdf)

    calc_df: pd.DataFrame = pd.concat(calc_dfs, axis=0)

    return calc_df


if __name__ == "__main__":
    cids: List[str] = ["USD", "EUR", "GBP", "AUD", "CAD"]
    xcats: List[str] = ["FXXR_NSA", "EQXR_NSA", "IRXR_NSA", "CDS_NSA"]

    start: str = "2000-01-01"
    end: str = "2020-12-31"

    df: pd.DataFrame = make_test_df(
        cids=cids,
        xcats=xcats,
        start=start,
        end=end,
    )

    hist_vols: pd.DataFrame = historic_portfolio_vol(
        df=df,
        sname="TEST",
        contids=[f"{cid}_{xcat}" for cid in cids for xcat in xcats],
        est_freq="m",
        lback_periods=21,
        lback_meth="ma",
        half_life=11,
        rstring="XR",
        start=start,
        end=end,
    )
