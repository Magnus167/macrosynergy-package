import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from typing import List, Union, Tuple

from macrosynergy.management.simulate_quantamental_data import make_qdf
from macrosynergy.management.shape_dfs import reduce_df

def proxy_pnl(
        df: pd.DataFrame,
        spos: str,
        contids: List[str],
        tcost_n: str = None,
        rcost_n: str = None,
        size_n: str = None,
        tcost_l: str = None,
        rcost_l: str = None,
        size_l: str = None,
        roll_freqs: dict = None,
        start: str = None,
        end: str = None,
        blacklist: dict = None,


):  
    """
    Calculates an approximate nominal PnL under consideration of transaction costs

    :param <pd.DataFrame> df:  standardized JPMaQS DataFrame with the necessary
        columns: 'cid', 'xcat', 'real_date' and 'value'.
        This dataframe must contain the contract-specific signals and possibly
        related return series (for vol-targeting).
    :param <str> spos: the name of the strategy positions in the dataframe in
        the format "<sname>_<pname>". 
        This must correspond to contract positions in the dataframe, which are categories
        of the format "<cid>_<ctype>_<sname>_<pname>". The strategy name <sname> has 
        usually been set by the `contract_signals` function and the string for <pname> by 
        the `notional_positions` function.
    :param <list[str]> contids: list of contract identifiers in the format 
        "<cid>_<ctype>". It must correspond to contract signals in the dataframe in the
        format "<cid>_<ctype>_<sname>_<pname>".
    :param <str> tcost_n: the postfix of the trading cost category for normal size. Values 
        are defined as the full bid-offer spread for a normal position size.
        This must correspond to trading a cost category "<cid>_<ctype>_<tcost_n>"
        in the dataframe. 
        Default is None: no trading costs are considered.
    :param <str> rcost_n: the postfix of the roll cost category for normal size. Values 
        are defined as the roll charges for a normal position size.
        This must correspond to a roll cost category "<cid>_<ctype>_<rcost_n>"
        in the dataframe. 
        Default is None: no trading costs are considered.
    :param <str> size_n: Normal size in USD million This must correspond to a normal
        trade size category "<cid>_<ctype>_<size_n>" in the dataframe.
        Default is None: all costs are are applied independent of size.
l   :param <str> tcost_l: the postfix of the trading cost category for large size.
        Large here is defined as 90% percentile threshold of trades in the market.
        Default is None: trading costs are are applied independent of size.
    :param <str> rcost_l: the postfix of the roll cost category for large size. Values 
        are defined as the roll charges for a large position size.
        This must correspond to a roll cost category "<cid>_<ctype>_<rcost_l>"
        in the dataframe. 
        Default is None: no trading costs are considered.
    :param <str> size_l: Large size in USD million. Default is None: all costs are
        are applied independent of size.
    :param <dict> roll_freqs: dictionary of roll frequencies for each contract type.
        This must use the contract types as keys and frequency string ("w", "m", or "q")
        as values. The default frequency for all contracts not in the dictionary is 
        "m" for monthly. Default is None: all contracts are rolled monthly.
    :param <str> start: the start date of the data. Default is None, which means that
        the start date is taken from the dataframe.
    :param <str> end: the end date of the data. Default is None, which means that
        the end date is taken from the dataframe.
    :param <dict> blacklist: a dictionary of contract identifiers to exclude from
        the calculation. Default is None, which means that no contracts are excluded.
    
    return: <pd.DataFrame> of the standard JPMaQS format with "GLB" (Global) as cross
        section and three categories "<sname>_<pname>_PNL" (total PnL in USD terms under
        consideration of transaction costs), "<sname>_<pname>_COST" (all imputed trading
        and roll costs in USD terms), and "<sname>_<pname>_PNLX" (total PnL in USD terms
        without consideration of transaction costs).

    N.B.: Transaction costs as % of notional are considered to be a linear function of 
        size, with the slope determined by the normal and large positions, if all relevant 
        series are applied.
    """

    pass