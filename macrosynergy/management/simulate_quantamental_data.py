import numpy as np
import pandas as pd
from statsmodels.tsa.arima_process import ArmaProcess
from typing import List, Tuple, Dict
from collections import defaultdict
import datetime


def simulate_ar(nobs: int, mean: float = 0, sd_mult: float = 1, ar_coef: float = 0.75):
    """
    Create an auto-correlated data-series as numpy array.

    :param <int> nobs: number of observations.
    :param <float> mean: mean of values, default is zero.
    :param <float> sd_mult: standard deviation multipliers of values, default is 1.
        This affects non-zero means.
    :param <float> ar_coef: autoregression coefficient (between 0 and 1): default is 0.75.

    return <np.array>: autocorrelated data series.
    """

    # Define relative parameters for creating an AR process.
    ar_params = np.r_[1, -ar_coef]
    ar_proc = ArmaProcess(ar_params)  # define ARMA process
    ser = ar_proc.generate_sample(nobs)
    ser = ser + mean - np.mean(ser)
    return sd_mult * ser / np.std(ser)

def dataframe_generator(df_cids: pd.DataFrame, df_xcats: pd.DataFrame,
                        cid: str, xcat: str):
    """
    Adjacent method used to construct the quantamental DataFrame.

    :param <pd.DataFrame> df_cids:
    :param <pd.DataFrame> df_xcats:
    :param <str> cid: individual cross-section.
    :param <str> xcat: individual category.

    """
    qdf_cols = ['cid', 'xcat', 'real_date', 'value']

    sdate = pd.to_datetime(max(df_cids.loc[cid, 'earliest'], df_xcats.loc[xcat,
                                                                          'earliest']))
    edate = pd.to_datetime(min(df_cids.loc[cid, 'latest'], df_xcats.loc[xcat,
                                                                        'latest']))
    all_days = pd.date_range(sdate, edate)
    work_days = all_days[all_days.weekday < 5]

    df_add = pd.DataFrame(columns=qdf_cols)
    df_add['real_date'] = work_days
    df_add['cid'] = cid
    df_add['xcat'] = xcat

    return df_add, work_days

def make_qdf(df_cids: pd.DataFrame, df_xcats: pd.DataFrame, back_ar: float = 0):
    """
    Make quantamental DataFrame with basic columns: 'cid', 'xcat', 'real_date', 'value'.

    :param <pd.DataFrame> df_cids: DataFrame with parameters by cid. Row indices are
        cross-sections. Columns are:
        'earliest': string of earliest date (ISO) for which country values are available;
        'latest': string of latest date (ISO) for which country values are available;
        'mean_add': float of country-specific addition to any category's mean;
        'sd_mult': float of country-specific multiplier of an category's standard
            deviation.
    :param <pd.DataFrame> df_xcats: dataframe with parameters by xcat. Row indices are
        cross-sections. Columns are:
        'earliest': string of earliest date (ISO) for which category values are
        available;
        'latest': string of latest date (ISO) for which category values are available;
        'mean_add': float of category-specific addition;
        'sd_mult': float of country-specific multiplier of an category's standard
        deviation;
        'ar_coef': float between 0 and 1 denoting set auto-correlation of the category;
        'back_coef': float, coefficient with which communal (mean 0, SD 1) background
        factor is added to category values.
    :param <float> back_ar: float between 0 and 1 denoting set auto-correlation of the
        background factor. Default is zero.

    :return <pd.DataFrame>: basic quantamental DataFrame according to specifications.
    """
    df_list = []

    if any(df_xcats['back_coef'] != 0):

        sdate = min(min(df_cids.loc[:, 'earliest']), min(df_xcats.loc[:, 'earliest']))
        edate = max(max(df_cids.loc[:, 'latest']), max(df_xcats.loc[:, 'latest']))
        all_days = pd.date_range(sdate, edate)
        work_days = all_days[all_days.weekday < 5]
        ser = simulate_ar(len(work_days), mean=0, sd_mult=1, ar_coef=back_ar)
        df_back = pd.DataFrame(index=work_days, columns=['value'])
        df_back['value'] = ser

    for cid in df_cids.index:
        for xcat in df_xcats.index:
            df_add, work_days = dataframe_generator(df_cids=df_cids, df_xcats=df_xcats,
                                                    cid=cid, xcat=xcat)

            ser_mean = df_cids.loc[cid, 'mean_add'] + df_xcats.loc[xcat, 'mean_add']
            ser_sd = df_cids.loc[cid, 'sd_mult'] * df_xcats.loc[xcat, 'sd_mult']
            ser_arc = df_xcats.loc[xcat, 'ar_coef']
            df_add['value'] = simulate_ar(len(work_days), mean=ser_mean, sd_mult=ser_sd,
                                          ar_coef=ser_arc)

            back_coef = df_xcats.loc[xcat, 'back_coef']
            # Add the influence of communal background series.
            if back_coef != 0:
                dates = df_add['real_date']
                df_add['value'] = df_add['value'] + \
                                  back_coef * df_back.loc[dates,
                                                          'value'].reset_index(drop=True)

            df_list.append(df_add)

    return pd.concat(df_list).reset_index(drop=True)

def make_qdf_black(df_cids: pd.DataFrame, df_xcats: pd.DataFrame, blackout: dict):
    """
    Make quantamental DataFrame with basic columns: 'cid', 'xcat', 'real_date', 'value'.
    In this DataFrame the column, 'value', will consist of Binary Values denoting whether
    the cross-section is active for the corresponding dates.

    :param <pd.DataFrame> df_cids: dataframe with parameters by cid. Row indices are
        cross-sections. Columns are:
    'earliest': string of earliest date (ISO) for which country values are available;
    'latest': string of latest date (ISO) for which country values are available;
    'mean_add': float of country-specific addition to any category's mean;
    'sd_mult': float of country-specific multiplier of an category's standard deviation.
    :param <pd.DataFrame> df_xcats: dataframe with parameters by xcat. Row indices are
        cross-sections. Columns are:
    'earliest': string of earliest date (ISO) for which category values are available;
    'latest': string of latest date (ISO) for which category values are available;
    'mean_add': float of category-specific addition;
    'sd_mult': float of country-specific multiplier of an category's standard deviation;
    'ar_coef': float between 0 and 1 denoting set autocorrelation of the category;
    'back_coef': float, coefficient with which communal (mean 0, SD 1) background
        factor is added to categoy values.
    :param <dict> blackout: Dictionary defining the blackout periods for each cross-
        section. The expected form of the dictionary is:
        {'AUD': (Timestamp('2000-01-13 00:00:00'), Timestamp('2000-01-13 00:00:00')),
        'USD_1': (Timestamp('2000-01-03 00:00:00'), Timestamp('2000-01-05 00:00:00')),
        'USD_2': (Timestamp('2000-01-09 00:00:00'), Timestamp('2000-01-10 00:00:00')),
        'USD_3': (Timestamp('2000-01-12 00:00:00'), Timestamp('2000-01-12 00:00:00'))}
        The values of the dictionary are tuples consisting of the start & end-date of the
        respective blackout period. Each cross-section could have potentially more than
        one blackout period on a single category, and subsequently each key will be
        indexed to indicate the number of periods.

    :return <pd.DataFrame>: basic quantamental DataFrame according to specifications with
        binary values.
    """

    df_list = []

    conversion = lambda t: (pd.Timestamp(t[0]), pd.Timestamp(t[1]))
    dates_dict = defaultdict(list)
    for k, v in blackout.items():
        v = conversion(v)
        dates_dict[k[:3]].append(v)

    # At the moment the blackout period is being applied uniformally to each category:
    # each category will experience the same blackout periods.
    for cid in df_cids.index:
        for xcat in df_xcats.index:

            df_add, work_days = dataframe_generator(df_cids=df_cids, df_xcats=df_xcats,
                                                    cid=cid, xcat=xcat)
            arr = np.repeat(0, df_add.shape[0])
            dates = df_add['real_date'].to_numpy()

            list_tuple = dates_dict[cid]
            for tup in list_tuple:

                start = tup[0]
                end = tup[1]

                condition_start = start.weekday() - 4
                condition_end = end.weekday() - 4

                # Will skip the associated blackout period because of the received
                # invalid date, if it is not within the respective data series' range,
                # but will continue to populate the dataframe according to the other keys
                # in the dictionary.
                # Naturally compare against the data-series' formal start & end date.
                if start < dates[0] or end > dates[-1]:
                    print("Blackout period date not within data series range.")
                    break
                # If the date falls on a weekend, change to the following Monday.
                elif condition_start > 0:
                    while start.weekday() > 4:
                        start += datetime.timedelta(days=1)
                elif condition_end > 0:
                    while end.weekday() > 4:
                        end += datetime.timedelta(days=1)

                index_start = next(iter(np.where(dates == start)[0]))
                count = 0
                while start != tup[1]:
                    if start.weekday() < 5:
                        count += 1
                    start += datetime.timedelta(days=1)

                arr[index_start:(index_start + count + 1)] = 1

            df_add['value'] = arr

            df_list.append(df_add)

    return pd.concat(df_list).reset_index(drop=True)


def generate_lines(sig_len: int,
                   style : str = 'linear') -> np.ndarray:
    style : str = '-'.join(style.strip().lower().split())
    lines: Dict[str, np.ndarray] = {
            "linear": np.arange(1, sig_len + 1) * 100 / sig_len,
            "decreasing-linear": np.arange(sig_len, 0, -1) * 100 / sig_len,
            "sharp-hill": np.concatenate(
                (
                    np.arange(1, sig_len // 4 + 1) * 100 / sig_len,
                    np.arange(sig_len // 4, sig_len // 4 * 3 + 1)[::-1] * 100 / sig_len,
                    np.arange(sig_len // 4 * 3, sig_len + 1) * 100 / sig_len,
                )
            ),
            "four-bit-sine": np.concatenate(
                (
                    np.arange(1, sig_len // 4 + 1) * 100 / sig_len,
                    np.arange(sig_len // 4, sig_len // 4 * 3 + 1)[::-1] * 100 / sig_len,
                    np.arange(sig_len // 4 * 3, sig_len + 1) * 100 / sig_len,
                )
            ),
            # sine wave with 1==sig_len peak=50, trough=-50
            "sine": np.sin(np.arange(1, sig_len + 1) * np.pi / (sig_len / 2)) * 50 + 50,
        }
    if style == "any":
        return np.random.choice(list(lines.values()))
    elif style == "all":
        return lines
    else:
        return lines.get(style, None)
    


def make_test_df(
    cids: List[str] = ["AUD", "CAD", "GBP"],
    xcats: List[str] = ["XR", "CRY"],
    start_date: str = "2010-01-01",
    end_date: str = "2020-12-31",
    prefer : str = 'any',
):
    """
    Generates a test dataframe with pre-defined values.
    These values are meant to be used for testing purposes only.
    The functions generates a standard quantamental dataframe with
    where the value column is populated with pre-defined values.
    These values are simple lines, or waves that are easy to identify
    between plots, and for generic testing purposes.
    """

    if isinstance(cids, str):
        cids = [cids]
    if isinstance(xcats, str):
        xcats = [xcats]

    dates : pd.DatetimeIndex = pd.date_range(start_date, end_date)
    
    df_list: List[pd.DataFrame] = []
    for cid in cids:
        for xcat in xcats:
            df_add: pd.DataFrame = pd.DataFrame({"cid": [cid], "xcat": [xcat]})
            df_add["real_date"] = pd.bdate_range(start_date, end_date)
            df_add["value"] = generate_lines(len(dates), prefer)
            df_list.append(df_add)

    return pd.concat(df_list).reset_index(drop=True)

if __name__ == "__main__":

    ser_ar = simulate_ar(100, mean=0, sd_mult=1, ar_coef=0.75)

    cids = ['AUD', 'CAD', 'GBP']
    xcats = ['XR', 'CRY']
    df_cids = pd.DataFrame(index=cids, columns=['earliest', 'latest', 'mean_add',
                                                'sd_mult'])
    df_cids.loc['AUD', ] = ['2010-01-01', '2020-12-31', 0.5, 2]
    df_cids.loc['CAD', ] = ['2011-01-01', '2020-11-30', 0, 1]
    df_cids.loc['GBP', ] = ['2011-01-01', '2020-11-30', -0.2, 0.5]

    df_xcats = pd.DataFrame(index=xcats, columns=['earliest', 'latest',
                                                  'mean_add', 'sd_mult', 'ar_coef',
                                                  'back_coef'])
    df_xcats.loc['XR', ] = ['2010-01-01', '2020-12-31', 0, 1, 0, 0.3]
    df_xcats.loc['CRY', ] = ['2011-01-01', '2020-10-30', 1, 2, 0.9, 0.5]

    dfd = make_qdf(df_cids, df_xcats, back_ar=0.75)