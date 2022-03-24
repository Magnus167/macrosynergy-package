
import numpy as np
import pandas as pd
from typing import List, Union
import statsmodels.api as sm
from macrosynergy.management.simulate_quantamental_data import make_qdf
from macrosynergy.management.shape_dfs import reduce_df


def date_alignment(main_asset: pd.Series, hedging_asset: pd.Series):
    """
    Method used to align the two Series over the same timestamps: the sample data for the
    endogenous & exogenous variables must match throughout the re-estimation calculation.

    :param <pd.DataFrame> main_asset: the return series of the asset that is being
        hedged.
    :param <pd.Series> hedging_asset: the return series of the asset being used to hedge
        against the main asset.

    :return <pd.Timestamp, pd.Timestamp>: the shared start and end date across the two
        series.
    """
    ma_dates = main_asset.index
    ha_dates = hedging_asset.index

    if ma_dates[0] > ha_dates[0]:
        start_date = ma_dates[0]
    else:
        start_date = ha_dates[0]

    if ma_dates[-1] > ha_dates[-1]:
        end_date = ha_dates[-1]
    else:
        end_date = ma_dates[-1]

    return start_date, end_date


def hedge_calculator(main_asset: pd.DataFrame, hedging_asset: pd.Series,
                     rdates: List[pd.Timestamp], cross_section: str,):
    """
    The hedging of a contract can be achieved by taking positions across an entire panel.
    Therefore, compute the hedge ratio for each cross-section across the defined panel.
    The sample of data used for hedging will increase according to the dates parameter:
    each date represents an additional number of timestamps where the numeracy is
    instructed by the "refreq" parameter.

    :param <pd.DataFrame> main_asset: the return series of the asset that is being
        hedged.
    :param <pd.Series> hedging_asset: the return series of the asset being used to hedge
        against the main asset.
    :param <List[pd.Timestamp]> rdates the dates controlling the frequency of
        re-estimation.
    :param <str> cross_section: cross-section responsible for the "hedging_asset" series.

    :return <pd.DataFrame>: returns a dataframe of the hedge ratios for the respective
        cross-section.
    """

    hedging_ratio = []

    s_date, e_date = date_alignment(main_asset=main_asset, hedging_asset=hedging_asset)

    main_asset = main_asset.truncate(before=s_date, after=e_date)
    hedging_asset = hedging_asset.truncate(before=s_date, after=e_date)

    for d in rdates[1:]:
        # Todo: only estimate if d implies observation > minobs
        Y = main_asset.loc[:d]
        X = hedging_asset.loc[:d]
        X = sm.add_constant(X)
        mod = sm.OLS(Y, X)
        results = mod.fit()
        hedging_ratio.append(results.params)

    no_dates = len(rdates)
    cid = np.repeat(cross_section, (no_dates - 1))
    dates = np.array(rdates)
    data = np.column_stack((cid, dates[1:], np.array(hedging_ratio)))
    # Todo: make sure that coefficinet is applied after the end date of estimation sample

    return pd.DataFrame(data=data, columns=['cid', 'real_date', 'intercept',
                                            'coefficient'])


def hedge_ratio(df: pd.DataFrame, xcat: str = None, cids: List[str] = None,
                hedge_return: str = None, start: str = None, end: str = None,
                blacklist: dict = None, meth: str = 'ols', oos: bool = True,
                refreq: str = 'm', min_obs: int = 24):

    """
    Return dataframe of hedge ratios for one or more return categories.
    
    :param <pd.Dataframe> df: standardized data frame with the following necessary columns:
        'cid', 'xcats', 'real_date' and 'value. Will contain all of the data across all
        macroeconomic fields.
    :param <str> xcat:  extended category denoting the return series for which the
        hedge ratios are calculated. In order to hedge against the main asset, compute
        hedging ratios across the panel. For instance, a possible strategy would be to
        hedge a range of local equity index positions against the S&P 500. The main asset
        is defined by the parameter "hedge_return": in the above example it would be
        represented by the postfix USD_EQ.
    :param <List[str]> cids: cross sections for which hedge ratios are calculated;
        default is all available for the category.
    :param <str> hedge_return: ticker of return of the hedge asset or basket. The
        parameter represents a single series. For instance, "USD_EQ".
    :param <str> start: earliest date in ISO format. Default is None and earliest date in
        df is used.
    :param <str> end: latest date in ISO format. Default is None and latest date in df is
        used.
    :param <dict> blacklist: cross-sections with date ranges that should be excluded from
        the sample of data used for the rolling regression. If an entire period of data
        is excluded by the blacklisting, where a period is defined by the frequency
        parameter "refreq", the regression coefficient will remain constant for that
        period, or all periods coinciding with the blacklist.
    :param <bool> oos: if True (default) hedge ratio are calculated out-of-sample,
        i.e. for the period subsequent to the estimation period at the given
        re-estimation frequency.
    :param <str> refreq: re-estimation frequency. Frequency at which hedge ratios are
        re-estimated. The re-estimation is conducted at the end of the period and
        fills all days of the following period. The re-estimation can be computed on a
        weekly, monthly, and quarterly frequency with the notation 'w', 'm', and 'q'
        respectively. The default frequency is monthly.
    :param <int> min_obs: the minimum number of observations required in order to start
        classifying a hedge ratio between the assets. The default value is 24 timestamps
        (business days).
    :param <str> meth: method to estimate hedge ratio. At present the only method is
        OLS regression.

    :return <pd.Dataframe> df: dataframe with hedge ratios, which are based on estimation
        of a sample prior to the timestamp of the hedge ratio.

    N.B.: A hedge ratio is the estimated sensitivity of the main return  with respect to
    the asset used for hedging. The ratio is recorded for the period after the estimation
    sample up the next update.
    
    """

    cols = ['cid', 'xcat', 'real_date', 'value']
    assert list(df.columns) == cols, f"Expects a standardised dataframe with columns: " \
                                     f"{cols}."
    # Todo: cols only need to be subset of columns.
    #  Added column (tickers) should not be problem because of reduce_df

    post_fix = hedge_return.split('_')
    error_hedge = "The expected form of the 'hedge_return' parameter is <cid_xcat>. The" \
                  "parameter expects to define a single series."
    assert len(post_fix) == 2, error_hedge
    # Todo: this could have >2 list elements (EUR_EQXR_NSA) => ['EUR', 'EQXR', 'NSA']

    xcat_hedge = post_fix[1]
    cid_hedge = post_fix[0]
    available_categories = df['xcat'].unique()
    xcat_error = f"Category, {xcat_hedge}, not defined in the dataframe. Available " \
                 f"categories are: {available_categories}."
    assert xcat_hedge in available_categories, xcat_error
    # Todo: check on ticker, as xcat is not guarantee that required cid is available

    error_xcat = f"The field, xcat, must be a string but received <{type(xcat)}>. Only" \
                 f" a single category is used to hedge against the main asset."
    assert isinstance(xcat, str), error_xcat

    error_hedging = f"The return category used to be hedged, {xcat}, is " \
                    f"not defined in the dataframe."
    assert xcat in list(available_categories), error_hedging

    refreq_options = ['w', 'm', 'q']
    error_refreq = f"The re-estimation frequency parameter must be one of the following:" \
                   f"{refreq_options}."
    assert refreq in refreq_options, error_refreq

    if xcat_hedge == xcat:
        cids.remove(cid_hedge)  # if hedged is main asset type its cid cannot be hedged

    dfd = reduce_df(df, xcats=[xcat], cids=cids, start=start, end=end,
                    blacklist=blacklist)

    dfw = dfd.pivot(index='real_date', columns='cid', values='value')
    dfw = dfw.dropna(axis=0, how="any")
    # Todo: show be how = "all" as longest, not shortest series determines hedge activity
    # Todo: just concat hedge asset series with inner join, so that time index is the
    #  shorter of hedged and hedging assets
    dates = dfw.index

    df_copy = df.copy()
    # Confirms both dataframes will be defined over the same time-period: asset being
    # hedged and the assets used for hedging.
    hedge_series = reduce_df(df_copy, xcats=[xcat_hedge], cids=cid_hedge, start=dates[0],
                             end=dates[-1], blacklist=blacklist)
    hedge_series = hedge_series.reset_index(drop=True)
    values = hedge_series['value'].to_numpy()
    hedge_series_d = hedge_series['real_date'].to_numpy()

    # Given the application above, the main asset can only be defined over a shorter
    # timeframe which would be the timestamps used for the subsequent code.
    main_asset = pd.Series(data=values, index=hedge_series_d)

    # Todo: methinks the above can be replaced by dates = dfw.asfreq('BM').index
    #  using {'w': 'W', 'm': 'BM', 'q': 'BQ'}

    dates_index = pd.date_range(dates[0], dates[-1], freq=refreq)
    dates_series = pd.Series(data=np.zeros(len(dates_index)), index=dates_index)
    dates_resample = dates_series.resample(refreq, axis=0).sum()
    dates_resample = list(dates_resample.index)
    dates_re = [pd.Timestamp(d) for d in dates_resample]

    # A "rolling" hedge ratio is computed for each cross-section across the defined
    # panel.
    aggregate = []
    for c in cids:
        series = dfw[c]
        hedge_data = hedge_calculator(main_asset=main_asset, hedging_asset=series,
                                      rdates=dates_re, cross_section=c)
        aggregate.append(hedge_data)

    hedge_df = pd.concat(aggregate).reset_index(drop=True)
    hedge_df['xcat'] = hedge_return

    cols = ['cid', 'xcat', 'real_date', 'intercept', 'coefficient']
    return hedge_df[cols]


if __name__ == "__main__":
    cids = ['AUD', 'CAD', 'GBP', 'USD', 'NZD']
    xcats = ['FXXR', 'GROWTHXR', 'INFLXR', 'EQXR']

    df_cids = pd.DataFrame(index=cids, columns=['earliest', 'latest', 'mean_add',
                                                'sd_mult'])

    df_cids.loc['AUD'] = ['2010-01-01', '2020-12-31', 0.5, 2]
    df_cids.loc['CAD'] = ['2011-01-01', '2020-11-30', 0, 1]
    df_cids.loc['GBP'] = ['2012-01-01', '2020-11-30', -0.2, 0.5]
    df_cids.loc['USD'] = ['2013-01-01', '2020-09-30', -0.2, 0.5]
    df_cids.loc['NZD'] = ['2002-01-01', '2020-09-30', -0.1, 2]

    df_xcats = pd.DataFrame(index=xcats, columns=['earliest', 'latest', 'mean_add',
                                                  'sd_mult', 'ar_coef', 'back_coef'])

    df_xcats.loc['FXXR'] = ['2010-01-01', '2020-10-30', 1, 2, 0.9, 1]
    df_xcats.loc['GROWTHXR'] = ['2012-01-01', '2020-10-30', 1, 2, 0.9, 1]
    df_xcats.loc['INFLXR'] = ['2013-01-01', '2020-10-30', 1, 2, 0.8, 0.5]
    df_xcats.loc['EQXR'] = ['2010-01-01', '2022-03-14', 0.5, 2, 0, 0.2]

    dfd = make_qdf(df_cids, df_xcats, back_ar=0.75)
    black = {'AUD': ['2010-01-01', '2014-01-04'], 'GBP': ['2010-01-01', '2013-12-31']}

    xcat_hedge = "EQXR"
    # S&P500.
    hedge_return = "USD_EQXR"
    df_hedge = hedge_ratio(df=dfd, xcat=xcat_hedge, cids=cids,
                           hedge_return=hedge_return, start='2010-01-01',
                           end='2020-10-30',
                           blacklist=black, meth='ols', oos=True,
                           refreq='m', min_obs=24)
    print(df_hedge)

    # Long position in S&P500 or the Nasdeq, and subsequently using US FX to hedge the
    # long position.
    xcats = 'FXXR'
    cids = ['USD']
    hedge_return = "USD_EQXR"
    xcat_hedge_two = hedge_ratio(df=dfd, xcat=xcats, cids=cids,
                                 hedge_return=hedge_return, start='2010-01-01',
                                 end='2020-10-30',
                                 blacklist=black, meth='ols', oos=True,
                                 refreq='m', min_obs=24)
    print(xcat_hedge_two)