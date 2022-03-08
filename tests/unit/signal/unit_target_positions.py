

import unittest
from macrosynergy.signal.target_positions import *
from macrosynergy.management.shape_dfs import reduce_df
from macrosynergy.panel.basket import Basket
from tests.simulate import make_qdf
import random
import pandas as pd
import numpy as np

class TestAll(unittest.TestCase):

    def dataframe_generator(self):

        self.__dict__['cids'] = ['AUD', 'GBP', 'NZD', 'USD']
        # Two meaningful fields and a third contrived category.
        self.__dict__['xcats'] = ['FXXR_NSA', 'EQXR_NSA', 'SIG_NSA']
        self.__dict__['ctypes'] = ['FX', 'EQ']
        self.__dict__['xcat_sig'] = 'FXXR_NSA'

        df_cids = pd.DataFrame(index=self.cids, columns=['earliest', 'latest',
                                                         'mean_add', 'sd_mult'])

        df_cids.loc['AUD'] = ['2010-01-01', '2020-12-31', 0, 1]
        df_cids.loc['GBP'] = ['2010-01-01', '2020-12-31', 0, 2]
        df_cids.loc['NZD'] = ['2010-01-01', '2020-12-31', 0, 3]
        df_cids.loc['USD'] = ['2010-01-01', '2020-12-31', 0, 4]

        df_xcats = pd.DataFrame(index=self.xcats, columns=['earliest', 'latest',
                                                           'mean_add', 'sd_mult',
                                                           'ar_coef', 'back_coef'])

        df_xcats.loc['FXXR_NSA'] = ['2010-01-01', '2020-12-31', 0, 1, 0, 0.2]
        df_xcats.loc['EQXR_NSA'] = ['2010-01-01', '2020-12-31', 0.5, 2, 0, 0.2]
        df_xcats.loc['SIG_NSA'] = ['2010-01-01', '2020-12-31', 0, 10, 0.4, 0.2]

        random.seed(2)
        dfd = make_qdf(df_cids, df_xcats, back_ar=0.75)

        self.__dict__['dfd'] = dfd

        black = {'AUD': ['2000-01-01', '2003-12-31'],
                 'GBP': ['2018-01-01', '2100-01-01']}

        self.__dict__['blacklist'] = black

        assert 'dfd' in vars(self).keys(), "Instantiation of DataFrame missing from " \
                                           "field dictionary."

        # Exclude the blacklist from the creation of the dataframe. All dates are used
        # for calculating the evolving volatility for the volatility targeting mechanism.
        dfd_reduced = reduce_df(df=self.dfd, xcats=[self.xcat_sig], cids=self.cids,
                                start='2012-01-01', end='2020-10-30',
                                blacklist=None)
        self.__dict__['dfd_reduced'] = dfd_reduced
        self.__dict__['df_pivot'] = dfd_reduced.pivot(index="real_date", columns="cid",
                                                      values="value")

    def test_unitary_positions(self):

        self.dataframe_generator()

        with self.assertRaises(AssertionError):
            # Testing the assertion on the scale parameter: required ['prop', 'dig'].
            # Pass in noise.
            scale = 'vtarg'
            position_df = target_positions(df=self.dfd, cids=self.cids,
                                           xcat_sig='FXXR_NSA',
                                           ctypes=['FX', 'EQ'], sigrels=[1, -1],
                                           ret='XR_NSA', start='2012-01-01',
                                           end='2020-10-30', scale=scale,
                                           cs_vtarg=0.1, posname='POS')

        # Unitary Position function should return a dataframe consisting of a single
        # category, the signal, and the respective dollar position: (in standard
        # deviations or a simple buy / sell recommendation).
        xcat_sig = 'FXXR_NSA'
        df_unit_pos = modify_signals(df=self.dfd, cids=self.cids, xcat_sig=xcat_sig,
                                     start='2012-01-01', end='2020-10-30', scale='dig',
                                     thresh=2.5)

        self.assertTrue(df_unit_pos['xcat'].unique().size == 1)
        self.assertTrue(np.all(df_unit_pos['xcat'] == xcat_sig))

        # Digital unitary position can be validated by summing the absolute values of the
        # 'value' column and validating that the summed value equates to the number of
        # rows.
        summation = np.sum(np.abs(df_unit_pos['value']))
        self.assertTrue(summation == df_unit_pos.shape[0])

        # Reduce the dataframe & check the logic is correct.
        condition = np.where(self.dfd_reduced['value'].to_numpy() < 0)[0]
        first_negative_index = next(iter(condition))

        val_column = df_unit_pos['value'].to_numpy()
        self.assertTrue(val_column[first_negative_index] == -1)

        # Little need to test the application of make_zn_scores(), as the function has
        # its own respective Unit Test but test on the dimensions.
        # If the minimum number of observations parameter is set to zero,
        # the dimensions of the reduced dataframe should match the output dataframe.
        df_unit_pos = modify_signals(df=self.dfd, cids=self.cids, xcat_sig=xcat_sig,
                                     start='2012-01-01', end='2020-10-30', scale='prop',
                                     min_obs=0, thresh=2.5)

        self.assertTrue(df_unit_pos.shape == self.dfd_reduced.shape)

    def test_start_end(self):

        self.dataframe_generator()
        ret = 'XR_NSA'
        contract_returns = [c + ret for c in self.ctypes]

        # Tractable function - requires few tests. Validate each contract type is held in
        # the dictionary, and its associated value is a tuple.
        # durations = start_end(self.dfd, contract_returns)

        # Function removed from source code.

    @staticmethod
    def row_return(dfd, date, c_return, sigrel):

        df_c_ret = dfd[dfd['xcat'] == c_return]
        df_c_ret = df_c_ret.pivot(index="real_date", columns="cid", values="value")
        df_c_ret *= sigrel

        return df_c_ret.loc[date]

    def test_cs_unit_returns(self):
        # The method is required for volatility targeting to adjust the respective
        # positions.
        self.dataframe_generator()

        sigrels = [1, -1]
        ret = 'XR_NSA'
        contract_returns = [c + ret for c in self.ctypes]
        xcat_sig = 'FXXR_NSA'

        dates = self.df_pivot.index
        dfd = reduce_df(df=self.dfd, xcats=self.xcats, cids=self.cids,
                        start='2012-01-02', end='2020-10-30',
                        blacklist=None)

        # The main purpose of cs_unit_returns is to aggregate the returns across the
        # respective panels. The signal, used to take positions, can determine the
        # position across multiple asset classes: Equity, Foreign Exchange etc.
        # Therefore, if there is the intention of volatility targeting, the volatility
        # should be computed across the panels (portfolio) which requires summing the
        # respective returns, and subsequently adjusting the position.

        # Test the number of sigrels matches the number of panels held in the parameter
        # "contract_returns".
        with self.assertRaises(AssertionError):
            sigrels_copy = [1, -1, 1]
            df_pos_vt = cs_unit_returns(df=dfd, contract_returns=contract_returns,
                                        sigrels=sigrels_copy, ret=ret)

        # The next test is to confirm the above logic. To achieve testing the aggregation
        # method, choose a date and confirm the return dataframe completes the binary
        # operation (including multiplying by the sigrels).

        df_pos_vt = cs_unit_returns(df=dfd, contract_returns=contract_returns,
                                    sigrels=sigrels, ret=ret)
        dates = df_pos_vt['real_date']
        date = dates.iloc[int(dates.shape[0] / 2)]
        # Returns across asset class.
        test_row = df_pos_vt[df_pos_vt['real_date'] == date]
        test_row = test_row[['cid', 'value']]
        test_dict = dict(zip(test_row['cid'], test_row['value']))

        fx_row = self.row_return(dfd=dfd, date=date, c_return=contract_returns[0],
                                 sigrel=sigrels[0])
        eq_row = self.row_return(dfd=dfd, date=date, c_return=contract_returns[1],
                                 sigrel=sigrels[1])
        manual_calculation = fx_row + eq_row
        manual_calculation = manual_calculation.to_dict()

        # The key will correspond to the cross-section and the value the associated
        # return across both assets.
        for k, v in test_dict.items():
            self.assertTrue(v == manual_calculation[k])

        # The final test is to validate that the first available date for the cross-asset
        # returns is "2012-01-02". If any dates are not shared across the two assets, the
        # respective dates will be removed from the return dataframe (used to compute
        # the volatility across the positions).
        first_date = str(dates.iloc[0].strftime("%Y-%m-%d"))
        self.assertTrue(first_date == "2012-01-02")

    def test_basket_handler(self):

        self.dataframe_generator()

        reduced_dfd = reduce_df(df=self.dfd, xcats=self.xcats, cids=self.cids,
                                blacklist=None)
        # The positions are computed across the panel (for every cross-section available
        # for that asset class). However, baskets can also be passed into the function
        # and the basket of contracts will represent a subset of the panel. Further, each
        # contract within the basket has a corresponding weight to adjust the position.
        # Therefore, test that the basket_handler() produces the correct weight-adjusted
        # positions for the contracts in the basket.

        xcat_sig = 'SIG_NSA'
        scale = 'prop'
        df_mods = modify_signals(df=reduced_dfd, cids=self.cids, xcat_sig=xcat_sig,
                                 scale=scale)

        # The position computed using the signal is used for multiple assets. The only
        # difference is the signal.
        df_mods_w = df_mods.pivot(index="real_date", columns="cid", values="value")

        # Create the basket: the basket will be a subset of the cross-sections present in
        # the panel.
        apc_contracts = ['AUD_FX', 'NZD_FX']
        basket_1 = Basket(df=reduced_dfd, contracts=apc_contracts, ret="XR_NSA",
                          cry=None)
        basket_1.make_basket(weight_meth="equal", max_weight=0.55,
                             basket_name="APC_FX")
        # Required wide, pivoted dataframe.
        dfw_wgs = basket_1.dict_wgs["APC_FX"]

        df_mods_w_output = basket_handler(df_mods_w=df_mods_w, df_c_wgts=dfw_wgs,
                                          contracts=apc_contracts)

        # The first test is to confirm that the position dataframe, used for the basket,
        # contains the same number of contracts, columns, as the basket itself.
        self.assertTrue(df_mods_w_output.shape[1] == len(apc_contracts))

        # Complete the manual calculation to test the method (weight-adjusted positions).
        df_mods_w = df_mods_w.reindex(sorted(df_mods_w.columns), axis=1)

        split = lambda b: b.split('_')[0]
        df_mods_w_basket = df_mods_w[list(map(split, apc_contracts))]

        # Confirm alignment of contracts.
        dfw_wgs = dfw_wgs.reindex(sorted(dfw_wgs.columns), axis=1)
        df_mods_w_basket = df_mods_w_basket.multiply(dfw_wgs.to_numpy())

        self.assertTrue(np.all(df_mods_w_basket.index == df_mods_w_basket.index))
        condition = df_mods_w_output.to_numpy() == df_mods_w_basket.to_numpy()
        self.assertTrue(np.all(condition))

    @staticmethod
    def basket_weight(reduced_dfd, df_mods_w, local_contracts, basket_name):
        """
        Method used to produce the weight adjusted positions for a basket. The weighting
        method chosen for the basket is fixed to inverse of the standard deviation.

        :param <pd.DataFrame> reduced_dfd: standardised dataframe.
        :param <pd.DataFrame> df_mods_w: target positions across the panel (the signal).
        :param <List[str]> local_contracts: contracts the basket is defined over.
        :param <str> basket_name: name of the respective basket.

        :return <pd.DataFrame> df_basket_pos: the weight-adjusted basket positions.
        """

        basket_1 = Basket(df=reduced_dfd, contracts=local_contracts, ret="XR_NSA",
                          cry=None)
        basket_1.make_basket(weight_meth="invsd", lback_meth="ma", lback_periods=21,
                             max_weight=0.55, remove_zeros=True,
                             basket_name=basket_name)
        # Pivoted weight dataframe.
        df_c_wgts = basket_1.dict_wgs[basket_name]

        # Return the weight adjusted target positions for the contract. This will be the
        # benchmark dataframe being tested.
        df_basket_pos = basket_handler(df_mods_w=df_mods_w, df_c_wgts=df_c_wgts,
                                       contracts=local_contracts)
        return df_basket_pos

    def test_consolidation_help(self):

        self.dataframe_generator()
        # If a basket of contracts are defined, their respective positions will be weight
        # adjusted. After the weight-adjusted positions are computed for the basket,
        # consolidate the positions on the shared contracts: intersection between the
        # panel and respective basket.
        # Therefore, check whether the above logic is implemented.

        # Further, it is worth noting that the basket should be a subset of the panel:
        # the panel is the complete set. Therefore, additional assertions are not
        # required.
        reduced_dfd = reduce_df(df=self.dfd, xcats=self.xcats, cids=self.cids,
                                blacklist=None)

        # Establish the targeted positions using the modified returns of the signal.
        xcat_sig = 'SIG_NSA'
        scale = 'prop'

        # The two defined sigrels are used for the panel FX and the basket
        # "apc_contracts."
        sigrels = [1, -1]

        # "ZN" postfix is the default postfix for "make_zn_scores()". Will return a
        # standardised dataframe.
        df_mods = modify_signals(df=reduced_dfd, cids=self.cids, xcat_sig=xcat_sig,
                                 scale=scale)
        df_mods_w = df_mods.pivot(index="real_date", columns="cid", values="value")

        cross_sections = lambda c: c.split('_')[0]
        apc_contracts = ['AUD_FX', 'NZD_FX']
        contract_cids = list(map(cross_sections, apc_contracts))
        non_basket_cids = [c for c in self.cids if c not in contract_cids]

        df_basket_pos = self.basket_weight(reduced_dfd, df_mods_w, apc_contracts,
                                           basket_name="APC_FX")

        # Convert both the panel & basket dataframes to standardised dataframes.
        df_basket_stack = df_basket_pos.stack().to_frame("value").reset_index()
        # Test dataframe.
        consolidate_df = consolidation_help(panel_df=df_mods, basket_df=df_basket_stack)

        # The consolidation will only be applicable on the intersection of contracts.
        # Therefore, check the other contract's positions remain the same.
        # Analyse on an arbitrary date.
        test_index = 1000
        test_date = df_basket_pos.index.to_numpy()[test_index]
        test_values = consolidate_df[consolidate_df['real_date'] == test_date]

        # Original positions: based on the panel, so columns will correspond to
        # cross-sections.
        df_mods_w_test_date = df_mods_w.loc[test_date]
        # Test date for the basket positions.
        df_basket_pos_test_date = df_basket_pos.loc[test_date]

        for c in non_basket_cids:
            logic = test_values[test_values['cid'] == c]['value']
            t_val = df_mods_w_test_date[c]
            logic = float(logic)
            self.assertTrue(abs(t_val - logic) < 0.000001)

        # Consolidate the positions computed for the basket contracts and the respective
        # panel.
        for c in contract_cids:
            logic = test_values[test_values['cid'] == c]['value']
            logic = float(logic)
            panel_val = df_mods_w_test_date[c]
            basket_val = df_basket_pos_test_date[c]
            # Consolidation operation.
            test = panel_val + basket_val
            self.assertTrue(abs(logic - test) < 0.000001)

    def test_consolidate_positions(self):

        self.dataframe_generator()
        # Conceals the function above and applies the logic to multiple baskets which are
        # consolidated to the associated number of panels.
        # Confirm the application of multiple baskets works.

        # Required multiple panels and baskets.

        reduced_dfd = reduce_df(df=self.dfd, xcats=self.xcats, cids=self.cids,
                                blacklist=None)

        # Establish the targeted positions using the modified returns of the signal.
        xcat_sig = 'SIG_NSA'
        scale = 'dig'
        # Modified the signal returns to digital: removes the magnitude of the position,
        # and exclusively classifies whether to take a long or short position in the
        # contract.
        df_mods = modify_signals(df=reduced_dfd, cids=self.cids, xcat_sig=xcat_sig,
                                 scale=scale)
        df_mods_w = df_mods.pivot(index="real_date", columns="cid", values="value")

        # The four defined sigrels are used for the two panels FX & EQ, and the baskets
        # "apc_contracts." and "west_contracts".
        sigrels = [1, -1, -0.5, 1.5]
        west_contracts = ['GBP_FX', 'USD_FX']
        apc_contracts = ['AUD_EQ', 'NZD_EQ']

        # The signal panel is used to establish positions in both panels. The two
        # dataframes below are the weight-adjusted target positions for the respective
        # baskets.
        df_basket_west = self.basket_weight(reduced_dfd, df_mods_w, west_contracts,
                                            basket_name="WST_FX")
        df_basket_apc = self.basket_weight(reduced_dfd, df_mods_w, apc_contracts,
                                           basket_name="APC_EQ")
        baskets = [df_basket_west, df_basket_apc]
        b_names = ["WST_FX", "APC_EQ"]
        dict_ = dict(zip(b_names, baskets))

        # Contract Types: FX & EQ.
        df_pos_cons = []
        for i, c in enumerate(self.ctypes):

            df_mods_copy = df_mods_w.copy()
            df_mods_copy *= sigrels[i]
            df_posi = df_mods_copy.stack().to_frame("value").reset_index()
            df_posi['xcat'] = c
            df_posi = df_posi.sort_values(['cid', 'xcat', 'real_date'])
            df_pos_cons.append(df_posi)

        # Two separate loops to make the intention explicit and confirm the logic. The
        # list, "df_pos_cons", after the iteration, will contain both the panel
        # dataframes and the basket dataframes.
        i = 0
        for k, v in dict_.items():
            sig = sigrels[i + len(self.ctypes)]
            v = v * sig
            df_posi = v.stack().to_frame("value").reset_index()
            df_posi['xcat'] = k
            df_posi = df_posi.sort_values(['cid', 'xcat', 'real_date'])
            df_pos_cons.append(df_posi)
            i += 1

        # Assert the consolidation has occurred correctly across both panels.
        df_pos_cons_output = consolidate_positions(df_pos_cons, self.ctypes)
        # The number of dataframes in the returned list should correspond to the number
        # of panels: the basket's position is added to the panel dataframe given the
        # basket is a subset of the panel.
        self.assertTrue(len(df_pos_cons_output) == len(self.ctypes))
        # Further, the expected category name, "xcat", of the dataframes inside the
        # returned list should be set to one of the contract types (each basket
        # dataframe will be subsumed under the panel dataframes: the contracts are the
        # same, so the positions are aggregated).
        for df in df_pos_cons_output:
            test_xcat = ''.join(df['xcat'].unique())
            self.assertTrue(test_xcat in self.ctypes)

        # Test the consolidation across the baskets.
        test_index = 1000
        test_date = df_mods_w.index.to_numpy()[test_index]

        # The basket's signal is -0.5.
        df_basket_west_test = df_basket_west.loc[test_date]
        # Basket position for its respective constituents.
        df_basket_west_test *= -0.5
        df_basket_west_test = df_basket_west_test.to_dict()

        # Panel position. Sigrel has already been applied.
        fx_panel = df_pos_cons[0]
        fx_panel_test = fx_panel[fx_panel['real_date'] == test_date]
        fx_panel_values = dict(zip(fx_panel_test['cid'], fx_panel_test['value']))

        for k, v in fx_panel_values.items():
            if k in df_basket_west_test.keys():
                fx_panel_values[k] += df_basket_west_test[k]

        fx_output, eq_output = df_pos_cons_output
        benchmark = fx_output[fx_output['real_date'] == test_date]
        benchmark_dict = dict(zip(benchmark['cid'], benchmark['value']))
        for k, v in benchmark_dict.items():
            self.assertTrue(abs(v - fx_panel_values[k]) < 0.00001)

    def test_target_positions(self):

        self.dataframe_generator()

        with self.assertRaises(AssertionError):
            # Test the assertion that the signal field must be present in the defined
            # dataframe. Will throw an assertion.
            xcat_sig = 'INTGRWTH_NSA'
            position_df = target_positions(df=self.dfd, cids=self.cids,
                                           xcat_sig=xcat_sig,
                                           ctypes=['FX', 'EQ'], sigrels=[1, -1],
                                           ret='XR_NSA', start='2012-01-01',
                                           end='2020-10-30', scale='prop',
                                           cs_vtarg=0.1, posname='POS')

        with self.assertRaises(AssertionError):
            # Testing the assertion on the scale parameter: required ['prop', 'dig'].
            # Pass in noise.
            scale = 'vtarg'
            position_df = target_positions(df=self.dfd, cids=self.cids,
                                           xcat_sig=xcat_sig,
                                           ctypes=['FX', 'EQ'], sigrels=[1, -1],
                                           ret='XR_NSA', start='2012-01-01',
                                           end='2020-10-30', scale=scale,
                                           cs_vtarg=0.1, posname='POS')

        with self.assertRaises(AssertionError):
            # Length of "sigrels" and "ctypes" must be the same. The number of "sigrels"
            # corresponds to the number of "ctypes" defined in the data structure passed
            # into target_positions().

            sigrels = [1, -1, 0.5, 0.25]
            ctypes = ['FX', 'EQ']
            position_df = target_positions(df=self.dfd, cids=self.cids,
                                           xcat_sig=xcat_sig,
                                           ctypes=self.ctypes, sigrels=sigrels,
                                           ret='XR_NSA',  start='2012-01-01',
                                           end='2020-10-30', scale=scale,
                                           cs_vtarg=0.1, posname='POS')

        # In the current test framework there are two contract types, FX & EQ, and the
        # signal used to subsequently construct a position is FXXR_NSA. If EQXR_NSA is
        # defined over a shorter timeframe, the position signal must be aligned to its
        # respective timeframe.
        # Check the logic matches the above description.

        # The returned standardised dataframe will consist of the signal and the
        # secondary category where the secondary category will be defined over a shorter
        # time-period.
        xcat_sig = 'FXXR_NSA'
        sigrels = [1, -1]
        output_df = target_positions(df=self.dfd, cids=self.cids,
                                     xcat_sig=xcat_sig, ctypes=self.ctypes,
                                     sigrels=sigrels, ret='XR_NSA',
                                     start='2012-01-01', end='2020-10-30', scale='dig',
                                     min_obs=0, cs_vtarg=None, posname='POS')
        # Testing the truncation feature. Concept might appear simple but implementation
        # is subtle. Isolate the secondary category in the output dataframe. The
        # dimensions should match.
        output_df['xcat'] = list(map(lambda str_: str_[4:-4], output_df['xcat']))

        df_eqxr = output_df[output_df['xcat'] == 'EQXR_NSA'].pivot(index="real_date",
                                                                   columns="cid",
                                                                   values="value")
        df_eqxr_input = self.dfd[self.dfd['xcat'] == 'EQXR_NSA'].pivot(index="real_date",
                                                                       columns="cid",
                                                                       values="value")
        # self.assertTrue(df_eqxr.shape == df_eqxr_input.shape)

        # Lastly, check the stacking procedure. In this instance, the output dateframe
        # should match the input dataframe.
        # Blacklist is applied after the position signals are established. Therefore, for
        # any dimensionality comparison, apply the blacklisting to the input dataframe.
        dfd = reduce_df(df=self.dfd, xcats=self.xcats, cids=self.cids,
                        start='2012-01-01', end='2020-10-30')
        # self.assertTrue(output_df.shape == dfd.shape)

        # Test the dimensions of the signal to confirm the differing size of the two
        # individual dataframes that are concatenated into a single structure. The output
        # dataframe should match the dimensions of the two respective inputs.
        df_signal = output_df[output_df['xcat'] == xcat_sig].pivot(index="real_date",
                                                                   columns="cid",
                                                                   values="value")
        df_signal_input = dfd[dfd['xcat'] == xcat_sig].pivot(index="real_date",
                                                             columns="cid",
                                                             values="value")
        # self.assertTrue(df_signal.shape == df_signal_input.shape)

        # A limited but valid test to determine the logic is correct for the volatility
        # target is to set the value equal to zero, and consequently all the
        # corresponding positions should also be zero. If zero volatility is required,
        # unable to take a position in an asset that has non-zero standard deviation.
        output_df = target_positions(df=self.dfd, cids=self.cids,
                                     xcat_sig=xcat_sig, ctypes=self.ctypes,
                                     sigrels=sigrels, ret='XR_NSA',
                                     start='2010-01-01', end='2020-12-31', scale='dig',
                                     cs_vtarg=0.0, posname='POS')
        # self.assertTrue(np.all(output_df['value'] == 0.0))

        # Final check is if the signal category is defined over the shorter timeframe
        # both contracts individual position dataframes should match the signal.
        xcat_sig = 'EQXR_NSA'
        output_df = target_positions(df=self.dfd, cids=self.cids,
                                     xcat_sig=xcat_sig, ctypes=self.ctypes,
                                     sigrels=sigrels, ret='XR_NSA',
                                     start='2010-01-01', end='2020-12-31', scale='dig',
                                     cs_vtarg=0.85, posname='POS')

        # Will not be able to compare against the signal's input dimensions because of
        # the application of volatility targeting and the associated lookback period.
        output_df['xcat'] = list(map(lambda str_: str_[4:-4], output_df['xcat']))
        df_signal = output_df[output_df['xcat'] == xcat_sig]
        df_fxxr = output_df[output_df['xcat'] == 'FXXR_NSA']

        # self.assertTrue(df_signal.shape == df_fxxr.shape)

        dfd = reduce_df(df=self.dfd, xcats=self.xcats, cids=self.cids,
                        start='2012-01-01', end='2020-10-30', blacklist=None)
        output_df = target_positions(df=dfd, cids=self.cids,
                                     xcat_sig='SIG_NSA', ctypes=['FX', 'EQ'],
                                     sigrels=[1, 0.5], ret='XR_NSA', start='2012-01-01',
                                     end='2020-10-30', scale='dig',
                                     cs_vtarg=None, posname='POS')
        # The signal is defined over the shortest timeframe. Therefore, both categories,
        # where a position is taken, will have a time index that matches the signal if
        # volatility targeting is set to None.
        df_sig = dfd[dfd['xcat'] == 'SIG_NSA']
        # self.assertTrue((df_sig.shape[0] * 2) == output_df.shape[0])


if __name__ == "__main__":

    unittest.main()