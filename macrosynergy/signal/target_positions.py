
import numpy as np
import pandas as pd
from typing import List, Union
from macrosynergy.management.shape_dfs import reduce_df
from macrosynergy.management.simulate_quantamental_data import make_qdf
from macrosynergy.panel.historic_vol import historic_vol
from macrosynergy.panel.make_zn_scores import *
from macrosynergy.panel.basket import Basket
import random


def modify_signals(df: pd.DataFrame, cids: List[str], xcat_sig: str, start: str = None,
                   end: str = None, scale: str = 'prop',  min_obs: int = 252,
                   thresh: float = None):

    """
    Calculate modified cross-section signals based on zn-scoring (proportionate method)
    or conversion to signs (digital method).

    :param <pd.Dataframe> df: standardized DataFrame containing the following columns:
        'cid', 'xcats', 'real_date' and 'value'.
    :param <List[str]> cids: cross sections of markets or currency areas in which
        positions should be taken.
    :param <str> xcat_sig: category that serves as signal across markets.
    :param <str> start: earliest date in ISO format. Default is None and earliest date
        for which the signal category is available is used.
    :param <str> end: latest date in ISO format. Default is None and latest date
        for which the signal category is available is used.
    :param <str> scale: method to translate signals into target positions:
        [1] Default is 'prop', means proportionate. In this case zn-scoring is applied
            to the signal based on the panel, with the neutral level set at zero.
            A 1 SD value translates into a USD1 position in the contract.
        [2] Method 'dig' means 'digital' and sets the individual position to either USD1
            long or short, depending on the sign of the signal.
    :param <int> min_obs: the minimum number of observations required to calculate
        zn_scores. Default is 252.
        Note: For the initial period of the signal time series in-sample
        zn-scoring is used.
    :param <float> thresh: threshold value beyond which zn-scores for propotionate
        position taking are winsorized. The threshold is the maximum absolute
        score value in standard deviations. The minimum is 1 standard deviation.

    :return <pd.Dataframe>: standardized dataframe, of modified signaks, using the 
        columns 'cid', 'xcat', 'real_date' and 'value'.

    """

    options = ['prop', 'dig']
    assert scale in options, f"The scale parameter must be either {options}"

    if scale == 'prop':

        df_ms = make_zn_scores(df, xcat=xcat_sig, sequential=True, cids=cids,
                               start=start, end=end, neutral='zero', pan_weight=1,
                               min_obs=min_obs, thresh=thresh)
    else:

        df_ms = reduce_df(df=df, xcats=[xcat_sig], cids=cids, start=start, end=end,
                          blacklist=None)
        df_ms['value'] = np.sign(df_ms['value'])

    return df_ms


def cs_unit_returns(df: pd.DataFrame, contract_returns: List[str],
                    sigrels: List[str], ret: str = 'XR_NSA'):

    """
    Calculate returns of composite unit positions (that jointly depend on one signal).

    :param <pd.Dataframe> df: standardized DataFrame containing the following columns:
        'cid', 'xcats', 'real_date' and 'value'.
    :param <List[str]> contract_returns: list of the contract return types.
    :param <List[float]> sigrels: respective signal for each contract type.
    :param <str> ret: postfix denoting the returns in % applied to the contract types.

    :return <pd.Dataframe>: standardized dataframe with the summed portfolio returns
        which are used to calculate the evolving volatility, using the columns 'cid',
        'xcat', 'real_date' and 'value'.

    """

    error_message = "Each individual contract requires an associated signal."
    assert len(contract_returns) == len(sigrels), error_message

    for i, c_ret in enumerate(contract_returns):

        df_c_ret = df[df['xcat'] == c_ret]
        df_c_ret = df_c_ret.pivot(index="real_date", columns="cid", values="value")

        df_c_ret = df_c_ret.sort_index(axis=1)
        df_c_ret *= sigrels[i]

        if i == 0:  # Add each return series of the contract.
            df_c_rets = df_c_ret
        else:
            df_c_rets += df_c_ret

    # Any dates not shared by all categories will be removed.
    df_c_rets.dropna(how='all', inplace=True)

    df_rets = df_c_rets.stack().to_frame("value").reset_index()
    df_rets['xcat'] = ret

    return df_rets

def basket_handler(df_mods_w: pd.DataFrame, df_c_wgts: pd.DataFrame,
                   contracts: List[str]):
    """
    Function designed to compute the target positions for the constituents of a basket.
    The function will return the corresponding basket dataframe of positions.

    :param <pd.DataFrame> df_mods_w: target position dataframe. Will be multiplied by the
        weight dataframe to establish the positions for the basket of constituents.
    :param <pd.DataFrame> df_c_wgts: weight dataframe used to adjust the positions of
        the basket of contracts.
    :param <dict> contracts: the constituents that make up each basket.

    :return <pd.Dataframe>: basket positions weight-adjusted.
    """

    error_1 = "df_c_wgts expects to receive a pd.DataFrame."
    assert isinstance(df_c_wgts, pd.DataFrame), error_1
    error_2 = "df_c_wgts expects a standardised pd.DataFrame produced by the Basket" \
              "Class."
    assert list(df_c_wgts.columns) == ["ticker", "real_date", "value"], error_2

    df_c_wgts = df_c_wgts.pivot(index="real_date", columns="ticker", values="value")
    split = lambda b: b.split('_')[0]

    cross_sections = list(map(split, contracts))

    # Sort the columns to align via cross-sections to conduct the multiplication. The
    # weight dataframe is formed using the respective contracts, so additional checks are
    # not required.
    dfw_wgs = df_c_wgts.reindex(sorted(df_c_wgts.columns), axis=1)
    w_columns = df_c_wgts.columns
    assert len(contracts) == len(w_columns)
    # The contract must be defined in the corresponding weight dataframe.
    weight_columns = ''.join(df_c_wgts.columns)
    for c in contracts:
        clause = weight_columns.find(c)
        assert clause != -1

    # Reduce to the cross-sections held in the respective basket.
    df_mods_w = df_mods_w[cross_sections]
    df_mods_w = df_mods_w.reindex(sorted(df_mods_w.columns), axis=1)

    # Adjust the target positions to reflect the weighting method. Align the pandas names
    # to allow for pd.DataFrame.multiply().
    dfw_wgs.columns = df_mods_w.columns
    df_mods_w = df_mods_w.multiply(dfw_wgs)

    return df_mods_w

def consolidation_help(panel_df: pd.DataFrame, basket_df: pd.DataFrame):
    """
    The function receives a panel dataframe and a basket of cross-sections of the same
    contract type. Therefore, aim to consolidate the targeted positions across the shared
    contracts.

    :param <pd.DataFrame> panel_df:
    :param <pd.DataFrame> basket_df:

    :return <pd.DataFrame, pd.DataFrame> returns the consolidated and reduced dataframes.
    """

    basket_cids = basket_df['cid'].unique()
    panel_cids = panel_df['cid'].unique()

    panel_copy = []
    for cid in panel_cids:
        indices = panel_df['cid'] == cid
        temp_df = panel_df[indices]

        if cid in basket_cids:
            basket_indices = basket_df['cid'] == cid
            b_values = basket_df[basket_indices]['value'].to_numpy()

            panel_values = temp_df['value'].to_numpy()
            consolidation = panel_values + b_values
            temp_df['value'] = consolidation
            panel_copy.append(temp_df)

            basket_indices = ~basket_indices
            basket_df = basket_df[basket_indices]
        else:
            panel_copy.append(temp_df)

    return pd.concat(panel_copy), basket_df

def consolidation_driver(data_frames: List[pd.DataFrame], ctypes: List[str]):
    """
    Method used to consolidate positions if baskets are used. The constituents of a
    basket will be a subset of one of the panels.

    :param <List[pd.DataFrame]> data_frames: list of the target position dataframes.
    :param <List[str]> ctypes:

    :return <List[pd.DataFrame]> list of dataframes having consolidated positions.
    """

    no_ctypes = len(ctypes)
    dict_ = dict(zip(ctypes[:no_ctypes], data_frames[:no_ctypes]))
    df_baskets = data_frames[no_ctypes:]

    split_2 = lambda b: b.split('_')[1]
    # Iterating exclusively through the basket dataframes.
    reduced_baskets = []
    for df in df_baskets:
        category = list(map(split_2, df['xcat'].to_numpy()))
        c_type = category[0]

        panel_df = dict_[c_type]
        panel_df, basket_df = consolidation_help(panel_df, basket_df=df)
        dict_[c_type] = panel_df
        reduced_baskets.append(basket_df)

    return list(dict_.values()) + reduced_baskets

def target_positions(df: pd.DataFrame, cids: List[str], xcat_sig: str, ctypes: List[str],
                     sigrels: List[float], baskets: dict = None,
                     df_c_wgts: Union[pd.DataFrame, List[pd.DataFrame]] = None,
                     ret: str = 'XR_NSA', start: str = None,
                     end: str = None, scale: str = 'prop', min_obs: int = 252,
                     thresh: float = None, cs_vtarg: float = None,
                     lback_periods: int = 21, lback_meth: str = 'ma',
                     half_life: int = 11, posname: str = 'POS'):

    """
    Converts signals into contract-specific target positions.

    :param <pd.Dataframe> df: standardized DataFrame containing at least the following
        columns: 'cid', 'xcats', 'real_date' and 'value'.
    :param <List[str]> cids: cross-sections of markets or currency areas in which
        positions should be taken.
    :param <str> xcat_sig: category that serves as signal across markets.
    :param <List[str]> ctypes: contract types that are traded across markets. They should
        correspond to return categories in the dataframe if the `ret` argument is
        appended. Examples are 'FX' or 'EQ'.
    :param <dict> baskets: a dictionary containing the name of each basket and the
        corresponding constituents. The key is of the form
        <cross_section>_<contract_type> and the value will be a list of the associated
        contracts. The key labels the basket. The value defines the contracts that are
        used for forming the basket. The default weighting method is for equal weights.
        An example would be:
        {'APC_FX' : ['AUD_FX', 'NZD_FX', 'JPY_FX'],
         'APC_EQ' : ['AUD_EQ', 'CNY_EQ', 'INR_EQ', 'JPY_EQ']}
    :param: <List[pd.DataFrame] or pd.DataFrame> df_c_wgts: weight dataframe used to
        adjust the positions of the basket of contracts. Or a List of weight dataframes
        if multiple baskets are passed.
    :param <List[float]> sigrels: values that translate the single signal into contract
        type and basket signals in the order defined by keys.
    :param <str> ret: postfix denoting the returns in % associated with contract types.
        For JPMaQS derivatives return data this is typically "XR_NSA".
        The returns are necessary for volatility target-based signals.
    :param <str> start: earliest date in ISO format. Default is None and earliest date
        for which the signal category is available is used.
    :param <str> end: latest date in ISO format. Default is None and latest date
        for which the signal category is available is used.
    :param <str> scale: method that translates signals into unit target positions:
        [1] Default is 'prop' for proportionate. In this case zn-scoring is applied
            to the signal based on the panel, with the neutral level set at zero.
            A 1 SD value translates into a USD1 position in the contract.
            This translation may apply winsorization through the `thresh` argument
        [2] Method 'dig' means 'digital' and sets the individual position to either USD1
            long or short, depending on the sign of the signal.
        Note that unit target positions may subsequently be calibrated to meet cross-
        section volatility targets.
    :param <int> min_obs: the minimum number of observations required to calculate
        zn_scores. Default is 252.
        Note: For the initial minimum period of the signal time series in-sample
        zn-scoring is used.
    :param <float> thresh: threshold value beyond which zn-scores for proportionate
        position taking are winsorized. The threshold is the maximum absolute
        score value in standard deviations. The minimum is 1 standard deviation.
    :param <float> cs_vtarg: This allows volatility targeting at the cross-section level.
        Default is None, but if a value is chosen then for each cross-section a unit
        position is defined as a position for which the annual return standard deviation
        is equal to that value.
        For example, a target of 10 and a cross-section signal of 0.5 standard deviations
        would translate into a target position that carries a recent historical
        annualized standard deviation of 5 dollars (or other currency units).
    :param <int>  lback_periods: Number of lookback periods over which volatility is
        calculated. Default is 21.
    :param <str> lback_meth: Lookback method to calculate the volatility.
        Default is "ma". Alternative is "ema", exponential moving average.
    :param <int> half_life: Refers to the half-time for "xma". Default is 11.
    :param <str> posname: postfix added to contract to denote position name.

    :return <pd.Dataframe>: standardized dataframe with daily target positions
        in USD, using the columns 'cid', 'xcat', 'real_date' and 'value'.

    Note: A target position differs from a signal insofar as it is a dollar amount and
          determines to what extent size of signal (as opposed to direction) matters.
          A target position also differs from an actual position in two ways. First,
          the actual position can only be aligned with the target with some lag. Second,
          the actual position will be affected by other considerations, such as
          risk management and assets under management.
    """

    # A. Initial checks

    categories = set(df['xcat'].unique())
    error_1 = "Signal category missing from the standardised dataframe."
    assert xcat_sig in categories, error_1
    error_2 = "Volatility Target must be numeric value."
    if cs_vtarg is not None:
        assert isinstance(cs_vtarg, (float, int)), error_2
    error_3 = "The number of signal relations must be equal to the number of contracts " \
              "and and baskets defined in 'ctypes'."
    if df_c_wgts is not None:
        error_4 = "pd.DataFrame of basket weights expected."
        assert isinstance(df_c_wgts, (list, pd.DataFrame)), error_4

    basket_names = []
    ctypes_baskets = ctypes + basket_names
    if baskets:
        basket_names = list(baskets.keys())
        ctypes_baskets = ctypes + basket_names

    clause = len(ctypes_baskets)
    assert len(sigrels) == clause, error_3
    assert isinstance(min_obs, int), "Minimum observation parameter must be an integer."

    cols = ['cid', 'xcat', 'real_date', 'value']
    assert set(cols) <= set(df.columns), f"df columns must contain {cols}."

    # B. Reduce frame to necessary data.

    df = df.loc[:, cols]
    contract_returns = [c + ret for c in ctypes]
    xcats = contract_returns + [xcat_sig]

    dfx = reduce_df(df=df, xcats=xcats, cids=cids, start=start,
                    end=end, blacklist=None)

    # C. Calculate and reformat modified cross-sectional signals.

    df_mods = modify_signals(df=dfx, cids=cids, xcat_sig=xcat_sig,
                             start=start, end=end, scale=scale, min_obs=min_obs,
                             thresh=thresh)  # (USD 1 per SD or sign)

    df_mods_w = df_mods.pivot(index="real_date", columns="cid", values="value")

    # D. Volatility target ratios (if required).

    use_vtr = False
    if isinstance(cs_vtarg, (int, float)):

        # D.1. Composite signal-related positions as basis for volatility targeting.

        df_csurs = cs_unit_returns(dfx, contract_returns=contract_returns,
                                   sigrels=sigrels)  # Gives cross-section returns.
        df_csurs = df_csurs[cols]

        # D.2. Calculate volatility adjustment ratios.

        df_vol = historic_vol(df_csurs, xcat=ret, cids=cids,
                              lback_periods=lback_periods, lback_meth=lback_meth,
                              half_life=half_life, start=start, end=end,
                              remove_zeros=True, postfix="")  # Gives unit position vols.

        dfw_vol = df_vol.pivot(index="real_date", columns="cid", values="value")
        dfw_vol = dfw_vol.sort_index(axis=1)
        dfw_vtr = 100 * cs_vtarg / dfw_vol  # vol-target ratio to be applied.
        use_vtr = True

    # E. Actual position calculation.

    data_frames = []
    ctypes_sigrels = dict(zip(ctypes_baskets, sigrels))
    if not isinstance(df_c_wgts, list):
        df_c_wgts = [df_c_wgts]

    df_c_wgts = iter(df_c_wgts)
    for k, v in ctypes_sigrels.items():

        # Copy of all modified signals. The single signal is being used to take a
        # position in multiple contracts. However, the position taken in each contract
        # will vary according to the specified signal.
        df_mods_copy = df_mods_w.copy()

        if use_vtr:
            # Apply vtr - scaling factor.
            dfw_pos_vt = df_mods_copy.multiply(dfw_vtr)
            dfw_pos_vt.dropna(how='all', inplace=True)
            df_mods_copy = dfw_pos_vt

        if k in basket_names:
            contracts = baskets[k]
            w_dataframe = next(df_c_wgts)
            df_mods_copy = basket_handler(df_mods_w=df_mods_copy, df_c_wgts=w_dataframe,
                                          contracts=contracts)

        # Allows for the signal being applied to the basket constituents on the original
        # dataframe.
        df_mods_copy *= v  # modified signal x sigrel = post-VT position.

        df_posi = df_mods_copy.stack().to_frame("value").reset_index()
        df_posi['xcat'] = k
        df_posi = df_posi.sort_values(['cid', 'xcat', 'real_date'])[cols]
        data_frames.append(df_posi)

    if baskets:
        data_frames = consolidation_driver(data_frames, ctypes)
    df_tpos = pd.concat(data_frames, axis=0, ignore_index=True)

    df_tpos['xcat'] += '_' + posname
    df_tpos['xcat'] = df_tpos['cid'] + '_' + df_tpos['xcat']
    df_tpos = df_tpos[cols]

    df_tpos = reduce_df(df=df_tpos, xcats=None, cids=None, start=start, end=end)

    df_tpos = df_tpos.sort_values(['cid', 'xcat', 'real_date'])[cols]

    return df_tpos.reset_index(drop=True)


if __name__ == "__main__":

    cids = ['AUD', 'GBP', 'NZD', 'USD']
    xcats = ['FXXR_NSA', 'EQXR_NSA', 'SIG_NSA']

    ccols = ['earliest', 'latest', 'mean_add', 'sd_mult']
    df_cids = pd.DataFrame(index=cids, columns=ccols)
    df_cids.loc['AUD'] = ['2010-01-01', '2020-12-31', 0, 1]
    df_cids.loc['GBP'] = ['2010-01-01', '2020-12-31', 0, 2]
    df_cids.loc['NZD'] = ['2010-01-01', '2020-12-31', 0, 3]
    df_cids.loc['USD'] = ['2010-01-01', '2020-12-31', 0, 4]

    xcols = ccols + ['ar_coef', 'back_coef']
    df_xcats = pd.DataFrame(index=xcats, columns=xcols)
    df_xcats.loc['FXXR_NSA'] = ['2010-01-01', '2020-12-31', 0, 1, 0, 0.2]
    df_xcats.loc['EQXR_NSA'] = ['2010-01-01', '2020-12-31', 0.5, 2, 0, 0.2]
    df_xcats.loc['SIG_NSA'] = ['2010-01-01', '2020-12-31', 0, 10, 0.4, 0.2]

    random.seed(2)
    dfd = make_qdf(df_cids, df_xcats, back_ar=0.75)
    black = {'AUD': ['2000-01-01', '2003-12-31'], 'GBP': ['2018-01-01', '2100-01-01']}

    xcat_sig = 'FXXR_NSA'

    position_df = target_positions(df=dfd, cids=cids,
                                   xcat_sig='SIG_NSA',
                                   ctypes=['FX', 'EQ'], sigrels=[1, 0.5], ret='XR_NSA',
                                   start='2012-01-01', end='2020-10-30',
                                   scale='prop', min_obs=252, cs_vtarg=5, posname='POS')

    position_df = target_positions(df=dfd, cids=cids, xcat_sig='FXXR_NSA',
                                   ctypes=['FX', 'EQ'], sigrels=[1, -1], ret='XR_NSA',
                                   start='2012-01-01', end='2020-10-30',
                                   scale='dig', cs_vtarg=0.1, posname='POS')

    # The secondary contract, EQXR_NSA, is defined over a shorter timeframe. Therefore,
    # on the additional dates, a valid position will be computed using the signal
    # category but a position will not be able to be taken for EQXR_NSA.
    position_df = target_positions(df=dfd, cids=cids, xcat_sig='FXXR_NSA',
                                   ctypes=['FX', 'EQ'], sigrels=[1, -1], ret='XR_NSA',
                                   start='2010-01-01', end='2020-12-31',
                                   scale='prop', cs_vtarg=None, posname='POS')

    # Testcase for both panel and individual basket performance.
    # Compute the returns on the Basket prior to calling the target positions, and pass
    # in the corresponding weight dataframe as a parameter. Therefore, the same weights
    # are involved in the target positions (adjust the positions according to the weight
    # dataframe).
    # The first testcase is a single contract.
    apc_contracts = ['AUD_FX', 'NZD_FX']
    basket_1 = Basket(df=dfd, contracts=apc_contracts, ret="XR_NSA",
                      cry=None, blacklist=black)
    basket_1.make_basket(weight_meth="equal", max_weight=0.55,
                         basket_name="GLB_EQUAL")
    df_weight = basket_1.return_weights("GLB_EQUAL")

    position_df = target_positions(df=dfd, cids=cids, xcat_sig='FXXR_NSA',
                                   ctypes=['FX', 'EQ'],
                                   baskets={'APC_FX': apc_contracts},
                                   df_c_wgts=df_weight,
                                   sigrels=[1, -1, -0.5], ret='XR_NSA',
                                   start='2010-01-01', end='2020-12-31',
                                   scale='prop', cs_vtarg=None, posname='POS')

    # The final dataframe will have consolidated the basket positions and the panel
    # positions on the intersection of contracts.
    print(position_df)

    # The second testcase is multiple contracts which will require the associated number
    # of weight dataframes.
    west_contracts = ['GBP_FX', 'USD_FX']
    apc_contracts = ['AUD_EQ', 'NZD_EQ']
    basket_2 = Basket(df=dfd, contracts=west_contracts, ret="XR_NSA",
                      cry=None, blacklist=black)
    basket_2.make_basket(weight_meth="equal", max_weight=0.55,
                         basket_name="GLB_EQUAL")
    df_weight_1 = basket_2.return_weights("GLB_EQUAL")

    basket_3 = Basket(df=dfd, contracts=apc_contracts, ret="XR_NSA",
                      cry=None, blacklist=black)
    basket_3.make_basket(weight_meth="equal", max_weight=0.55,
                         basket_name="GLB_EQUAL")
    df_weight_2 = basket_3.return_weights("GLB_EQUAL")
    df_weight = [df_weight_1, df_weight_2]

    position_df = target_positions(df=dfd, cids=cids, xcat_sig='FXXR_NSA',
                                   ctypes=['FX', 'EQ'],
                                   baskets={'WST_FX': west_contracts,
                                            'APC_EQ': apc_contracts},
                                   df_c_wgts=df_weight,
                                   sigrels=[1, -1, -0.5, 1.5], ret='XR_NSA',
                                   start='2010-01-01', end='2020-12-31',
                                   scale='prop', cs_vtarg=None, posname='POS')
    print(position_df)