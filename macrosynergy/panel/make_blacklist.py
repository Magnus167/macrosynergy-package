import numpy as np
import pandas as pd
from typing import List
from itertools import groupby
import random
from macrosynergy.management.shape_dfs import reduce_df
from macrosynergy.management.simulate_quantamental_data import make_qdf

def make_blacklist(df: pd.DataFrame, xcat: str, cids: List[str] = None,
                   start: str = None, end: str = None):

    """
    Converts binary category of standardized dataframe into a standardized dictionary
    that can serve as a blacklist for cross-sections in further analyses

    :param <pd.Dataframe> df: standardized DataFrame with following columns:
        'cid', 'xcats', 'real_date' and 'value'.
    :param <str> xcat: category with binary values, where 1 means blacklisted and 0 means
        not blacklisted.
    :param List<str> cids: list of cross-sections which are considered in the formation
        of the blacklist. Per default, all available cross sections are considered.
    :param <str> start: earliest date in ISO format. Default is None and earliest date
        for which the respective category is available is used.
    :param <str> end: latest date in ISO format. Default is None and latest date
        for which the respective category is available is used.

    :return <dict>: standardized dictionary with cross-sections as keys and tuples of
        start and end dates of the blacklist periods in ISO formats as values.
        If one cross section has multiple blacklist periods, numbers are added to the
        keys (i.e. TRY_1, TRY_2, etc.)
    """

    assert all(list(map(lambda val: val == 1 or val == 0), df['value'].to_numpy()))

    df = reduce_df(df=df, xcats=[xcat], cids=cids, start=start, end=end)
    df_pivot = df.pivot(index='real_date', columns='cid', values='value')

    dates = df_pivot.index
    cids_df = list(df_pivot.columns)

    dates_dict = {}
    for cid in cids_df:
        index_tr = 0
        count = 0

        column = df_pivot[cid]
        cut_off = column.last_valid_index()
        condition = np.where(dates == cut_off)[0]
        cut_off = next(iter(condition))

        column = column.to_numpy()[:(cut_off + 1)]

        # See Itertools documentation for further description. Will return a Generator
        # Object.
        for k, v in groupby(column):
            v = list(v)  # Instantiate the iterable in memory.
            length = len(v)

            if not sum(v) ^ 0:
                count += 1
                dates_dict[cid + '_' + str(count)] = (
                dates[index_tr], dates[index_tr + (length - 1)])

            index_tr += length

    return dates_dict


if __name__ == "__main__":

    cids = ['AUD', 'GBP', 'NZD', 'USD']

    xcats = ['FXXR_NSA', 'FXCRY_NSA', 'EQXR_NSA', 'EQCRY_NSA']

    df_cids = pd.DataFrame(index=cids, columns=['earliest', 'latest', 'mean_add',
                                                'sd_mult'])

    df_cids.loc['AUD'] = ['2010-01-01', '2020-12-31', 0, 1]
    df_cids.loc['GBP'] = ['2011-01-01', '2020-11-30', 0, 2]
    df_cids.loc['NZD'] = ['2012-01-01', '2020-12-31', 0, 3]
    df_cids.loc['USD'] = ['2013-01-01', '2020-12-31', 0, 4]

    df_xcats = pd.DataFrame(index=xcats, columns=['earliest', 'latest', 'mean_add',
                                                  'sd_mult', 'ar_coef', 'back_coef'])
    df_xcats.loc['FXXR_NSA'] = ['2010-01-01', '2020-12-31', 0, 1, 0, 0.2]
    df_xcats.loc['FXCRY_NSA'] = ['2011-01-01', '2020-10-30', 1, 1, 0.9, 0.5]
    df_xcats.loc['EQXR_NSA'] = ['2012-01-01', '2020-10-30', 0.5, 2, 0, 0.2]
    df_xcats.loc['EQCRY_NSA'] = ['2013-01-01', '2020-10-30', 1, 1, 0.9, 0.5]

    random.seed(2)
    dfd = make_qdf(df_cids, df_xcats, back_ar=0.75)

    print(dfd)

