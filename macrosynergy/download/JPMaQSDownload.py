""" JPMaQS Download Interface """

from typing import List
import pandas as pd
import numpy as np
from collections import defaultdict
import warnings
import json, yaml
import os
from macrosynergy.download import dq_api

import logging
logger = logging.getLogger(__name__)

def array_construction(metrics: List[str], output_dict: dict,
                        debug: bool, sequential: bool):
    """
    Helper function that will pass through the dictionary and aggregate each
    time-series stored in the interior dictionary. Will return a single dictionary
    where the keys are the tickers and the values are the aggregated time-series.

    :param <List[str]> metrics: metrics requested from the API.
    :param <dict> output_dict: nested dictionary where the keys are the tickers and
        the value is itself a dictionary. The interior dictionary's keys will be the
        associated metrics and the values will be their respective time-series.
    :param <bool> debug: used to understand any underlying issue.
    :param <bool> sequential: if series are not returned, potentially the fault of
        the threading mechanism, isolate each Ticker and run sequentially.

    """

    modified_dict = {}
    d_frame_order = ['real_date'] + metrics

    ticker_list = []
    for k, v in output_dict.items():

        available_metrics = set(v.keys())
        expected_metrics = set(d_frame_order)

        missing_metrics = list(expected_metrics.difference(available_metrics))
        if not missing_metrics:
            # Aggregates across all metrics requested and order according to the
            # prescribed list.
            ticker_df = pd.DataFrame.from_dict(v)[d_frame_order]

            modified_dict[k] = ticker_df.to_numpy()

        elif missing_metrics and not sequential:
            # If a requested metric has not been returned, its absence could be
            # ascribed to a potential data leak from multithreading. Therefore,
            # collect the respective tickers, defined over each metric, and run
            # the requests sequentially to avoid any scope for data leakage.

            temp_list = ['DB(JPMAQS,' + k + ',' + m + ')' for m in metrics]
            ticker_list += temp_list

            if debug:
                print(
                    f"The ticker, {k}, is missing the metric(s) "
                    f"'{missing_metrics}' whilst the requests are running "
                    f"concurrently - will check the API sequentially."
                )
        elif sequential and debug:
            print(
                f"The ticker, {k}, is missing from the API after "
                f"running sequentially - will not be in the returned "
                f"DataFrame."
            )
        else:
            continue

    return modified_dict, ticker_list

def isolate_timeseries(
    # self,
    list_,
    metrics: List[str],
    debug: bool,
    sequential: bool
):
    """
    Isolates the metrics, across all categories & cross-sections, held in the List,
    and concatenates the time-series, column-wise, into a single structure, and
    subsequently stores that structure in a dictionary where the dictionary's
    keys will be each Ticker.
    Will validate that each requested metric is available, in the data dictionary,
    for each Ticker. If not, will run the Tickers sequentially to confirm the issue
    is not ascribed to multithreading overloading the load balancer.

    :param <List[dict]> list_: returned from DataQuery.
    :param <List[str]> metrics: metrics requested from the API.
    :param <bool> debug: used to understand any underlying issue.
    :param <bool> sequential: if series are not returned, potentially the fault of
        the threading mechanism, isolate each Ticker and run sequentially.

    :return: <dict> modified_dict.
    """
    output_dict = defaultdict(dict)
    size = len(list_)
    if debug:
        print(f"Number of returned expressions from JPMaQS: {size}.")

    unavailable_series = []
    # Each element inside the List will be a dictionary for an individual Ticker
    # returned by DataQuery.
    for r in list_:

        dictionary = r["attributes"][0]
        ticker = dictionary["expression"].split(",")
        metric = ticker[-1][:-1]

        ticker_split = ",".join(ticker[1:-1])
        ts_arr = np.array(dictionary["time-series"])

        # Catches tickers that are defined correctly but will not have a valid
        # associated series. For example, "USD_FXXR_NSA" or "NLG_FXCRR_VT10". The
        # request to the API will return the expression but the "time-series" value
        # will be a None Object.
        # Occasionally, on large requests, DataQuery will incorrectly return a None
        # Object for a series that is available in the database.
        if ts_arr.size == 1:
            unavailable_series.append(ticker_split)

        else:
            if ticker_split not in output_dict.keys():
                output_dict[ticker_split]["real_date"] = ts_arr[:, 0]
                output_dict[ticker_split][metric] = ts_arr[:, 1]
            # Each encountered metric should be unique and one of "value", "grading",
            # "eop_lag" or "mop_lag".
            else:
                output_dict[ticker_split][metric] = ts_arr[:, 1]

    output_dict_c = output_dict.copy()

    modified_dict, ticker_list = array_construction(
        metrics=metrics, output_dict=output_dict_c, debug=debug,
        sequential=sequential
    )
    if debug:
        print(f"The number of tickers requested that are unavailable is: "
                f"{len(unavailable_series)}.")
        # __dict__["unavailable_series"] = unavailable_series

    return modified_dict, output_dict, ticker_list

def column_check(v, col, no_cols, debug):
    """
    Checking the values of the returned TimeSeries.

    :param <np.array> v:
    :param <integer> col: used to isolate the column being checked.
    :param <integer> no_cols: number of metrics requested.
    :param <bool> debug:

    :return <bool> condition.
    """
    returns = list(v[:, col])
    condition = all([isinstance(elem, type(None)) for elem in returns])

    if condition:
        other_metrics = list(v[:, 2:no_cols].flatten())

        if debug and all([isinstance(e, type(None)) for e in other_metrics]):
            warnings.warn("Error has occurred in the Database.")

    return condition

def valid_ticker(
    # self, 
    _dict, 
    suppress_warning, 
    debug):
    """
    Iterates through each Ticker and determines whether the Ticker is held in the
    Database or not. The validation mechanism will isolate each column, in all the
    Tickers held in the dictionary, where the columns reflect the metrics passed,
    and validates that each value is not a NoneType Object. If all values are
    NoneType Objects, the Ticker is not valid, and it will be popped from the
    dictionary.

    :param <dict> _dict:
    :param <bool> suppress_warning:
    :param <bool> debug:

    :return: <dict> dict_copy.
    """

    ticker_missing = 0
    dict_copy = _dict.copy()

    for k, v in _dict.items():
        no_cols = v.shape[1]
        condition = column_check(v, col=1, no_cols=no_cols, debug=debug)

        if condition:
            ticker_missing += 1
            dict_copy.pop(k)

            if not suppress_warning:
                print(f"The ticker, {k}), does not exist in the Database.")

    print(f"Number of missing time-series from the Database: {ticker_missing}.")
    return dict_copy

def dataframe_wrapper(_dict, no_metrics, original_metrics):
    """
    Receives a Dictionary containing every Ticker and the respective time-series data
    held inside an Array. Will iterate through the dictionary and stack each Array
    into a single DataFrame retaining the order both row-wise, in terms of cross-
    sections, and column-wise, in terms of the metrics.

    :param <dict> _dict:
    :param <Integer> no_metrics: Number of metrics requested.
    :param <List[str]> original_metrics: Order of the metrics passed.

    :return: pd.DataFrame: ['cid', 'xcat', 'real_date'] + [original_metrics]
    """

    tickers_no = len(_dict.keys())
    length = list(_dict.values())[0].shape[0]

    arr = np.empty(shape=(length * tickers_no, 3 + no_metrics), dtype=object)

    i = 0
    for k, v in _dict.items():

        ticker = k.split("_")

        cid = ticker[0]
        xcat = "_".join(ticker[1:])

        cid_broad = np.repeat(cid, repeats=v.shape[0])
        xcat_broad = np.repeat(xcat, repeats=v.shape[0])
        data = np.column_stack((cid_broad, xcat_broad, v))

        row = i * v.shape[0]
        arr[row: row + v.shape[0], :] = data
        i += 1

    columns = ["cid", "xcat", "real_date"]
    cols_output = columns + original_metrics

    df = pd.DataFrame(data=arr, columns=cols_output)

    df["real_date"] = pd.to_datetime(df["real_date"], yearfirst=True)
    df = df[df["real_date"].dt.dayofweek < 5]
    df = df.fillna(value=np.nan)
    df = df.reset_index(drop=True)

    for m in original_metrics:
        df[m] = df[m].astype(dtype=np.float32)

    df.real_date = pd.to_datetime(df.real_date)
    return df



class JPMaQSDownload(object):
    def import_credentials(self, credentials_file : str):
        if not os.path.exists(credentials_file):
            raise FileNotFoundError(f"Credentials file not found at {credentials_file}")
    
        if credentials_file.endswith(".json"):
            with open(credentials_file, "r") as f:
                credentials = json.load(f)
        elif credentials_file.endswith(".yaml"):
            with open(credentials_file, "r") as f:
                credentials = yaml.load(f, Loader=yaml.FullLoader)
        else:
            raise ValueError("Credentials file must be either a JSON or YAML file")
        
        client_id = credentials["client_id"]
        client_secret = credentials["client_secret"]
        return client_id, client_secret            

            

        
    def __init__(
            self, 
            oauth : bool =True,
            credentials_file : str = 'client_credentials.json',
            debug : bool =False,
            suppress_warning : bool =False,
            **kwargs):

        self.debug = debug
        self.suppress_warning = suppress_warning
        
        proxy = kwargs.get('proxy', None)
        
        if oauth:
            client_id, client_secret = self.import_credentials(credentials_file)
            dq_args = {'client_id': client_id, 'client_secret': client_secret, 'proxy': proxy}
        else:
            username = kwargs.get('username', None)
            password = kwargs.get('password', None)
            crt = kwargs.get('crt', None)
            key = kwargs.get('key', None)
            dq_args = {'username': username, 'password': password, 'crt': crt, 'key': key, 'proxy': proxy}
        
        dq_args['debug'] = debug
        dq_args['suppress_warning'] = suppress_warning
        dq_args['oauth'] = oauth
        
        self.dq_args = dq_args
        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            e_str = f"{exc_type} {exc_value} {traceback}"
            logger.error(e_str)
            raise exc_type(exc_value)
        else:
            return True
        
    def download(self,
                    tickers=None,
                    xcats=None,
                    cids=None,
                    metrics=['value'],
                    start_date='2000-01-01',
                    end_date=None,
                    suppress_warning=False,
                    debug=False
    ):
        if (cids is None) & (xcats is not None):
            cids_dmca = ["AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NOK", "NZD", "SEK",
                            "USD"]  # DM currency areas
            cids_dmec = ["DEM", "ESP", "FRF", "ITL", "NLG"]  # DM euro area countries
            cids_latm = ["BRL", "COP", "CLP", "MXN", "PEN"]  # Latam countries
            cids_emea = ["HUF", "ILS", "PLN", "RON", "RUB", "TRY", "ZAR"]  # EMEA countries
            cids_emas = ["CZK", "CNY", "IDR", "INR", "KRW", "MYR", "PHP", "SGD", "THB",
                            "TWD"]  # EM Asia countries
            cids_dm = cids_dmca + cids_dmec
            cids_em = cids_latm + cids_emea + cids_emas
            cids = sorted(cids_dm + cids_em)  # Standard default.
            
        if isinstance(metrics, str):
            metrics = [metrics]
        if isinstance(xcats, str):
            xcats = [xcats]
        if isinstance(cids, str):
            cids = [cids]
        
        if isinstance(tickers, str):
            tickers = [tickers]
        elif tickers is None:
            tickers = []
                
        assert isinstance(metrics, list), "Metrics must be a list of strings"
        assert isinstance(xcats, list), "Xcats must be a list of strings"
        assert isinstance(cids, list), "Cids must be a list of strings"
        assert isinstance(tickers, list), "Tickers must be a list of strings"

        for metric in metrics:
            assert metric in [
                "value",
                "eop_lag",
                "mop_lag",
                "grading"], f"Incorrect metric passed: {metric}."
        
        if xcats is not None:
            add_tix = [cid + "_" + xcat for cid in cids for xcat in xcats]
            tickers = tickers + add_tix

        with dq_api.Interface(**self.dq_args) as dq:
            df = dq.get_data(tickers=tickers, metrics=metrics, start_date=start_date, end_date=end_date)
            
            if (not isinstance(df, pd.DataFrame)) or (df.empty):
                logger.warning("No data returned from DataQuery")
                raise ValueError("No data returned from DataQuery")

            
        