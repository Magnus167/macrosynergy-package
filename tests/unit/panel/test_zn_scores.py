
import unittest
import numpy as np
import pandas as pd
from itertools import groupby
from random import randint, choice, shuffle, seed
from collections import defaultdict

from macrosynergy.management.simulate_quantamental_data import make_qdf
from macrosynergy.management.shape_dfs import reduce_df
from macrosynergy.panel.make_zn_scores import pan_neutral, cross_neutral, make_zn_scores, nan_insert


cids = ['AUD', 'CAD', 'GBP']
xcats = ['CRY', 'XR']
df_cids = pd.DataFrame(index=cids, columns=['earliest', 'latest', 'mean_add', 'sd_mult'])
df_cids.loc['AUD', :] = ['2010-01-01', '2020-12-31', 0.5, 2]
df_cids.loc['CAD', :] = ['2011-01-01', '2020-11-30', 0, 1]
df_cids.loc['GBP', :] = ['2012-01-01', '2020-11-30', -0.2, 0.5]

df_xcats = pd.DataFrame(index=xcats, columns=['earliest', 'latest', 'mean_add', 'sd_mult', 'ar_coef', 'back_coef'])
df_xcats.loc['CRY', :] = ['2010-01-01', '2020-10-30', 1, 2, 0.9, 0.5]
df_xcats.loc['XR', :] = ['2011-01-01', '2020-12-31', 0, 1, 0, 0.3]

dfd = make_qdf(df_cids, df_xcats, back_ar=0.75)  # standard df for tests
# Todo: Use this as basis of all tests that require standard dataframe
dfw = dfd[dfd['xcat']=='CRY'].pivot(index='real_date', columns='cid', values='value')
# Todo: Use this as basis of all tests that require a wide dataframe


class TestAll(unittest.TestCase):

    def test_pan_neutral(self):

        ar_neutral = pan_neutral(dfw, neutral='mean', sequential=True)
        self.assertIsInstance(ar_neutral, np.ndarray)  # check type of output
        self.assertTrue(dfw.shape[0] == len(ar_neutral))  # test length of neutral array

        ar_neutral = pan_neutral(dfw, neutral='mean', sequential=False)
        self.assertEqual(ar_neutral[0], dfw.stack().mean())  # check first value equal to panel mean
        self.assertEqual(ar_neutral[dfw.shape[0]-1], dfw.stack().mean())  # check also last value equal to panel mean

        ar_neutral = pan_neutral(dfw, neutral='mean', sequential=True)
        self.assertEqual(ar_neutral[999], dfw.iloc[0:1000, :].stack().mean())

        # Todo: same for median


    def test_cross_neutral(self):

        # Todo: same as above

        arr = np.linspace(1, 100, 100, dtype = np.float32)
        arr = arr.reshape((20, 5))
        columns = arr.shape[1]
        columns = ['Series_' + str(i + 1) for i in range(columns)]
        df = pd.DataFrame(data=arr, columns=columns)

        neutral = choice(['mean', 'median', 'zero'])
        sequential = choice([True, False])

        arr_neutral = cross_neutral(df, neutral, sequential)
        self.assertIsInstance(arr_neutral, np.ndarray)  # check correct type

        df_shape = df.shape
        self.assertEqual(df_shape, arr_neutral.shape)  # check correct dimensions

        ## Test the Cross_Sectional median algorithm's functionality with a contrived data set.
        ## Generate a two dimensional Array consisting of an iterative sequence, F(x) = (x + 1), where the input is the first column's index, and the adjacent column will host the sequence in reverse.
        ## If the Cross-Sectional Rolling Median algorithm is correct, the difference between the two columns will be the input into the aforementioned function in reserve.
        size = randint(1, 115)
        
        input_ = list(range(0, size, 1))
        col_1 = list(map(lambda x: x + 1, input_))
        col_2 = list(reversed(col_1))
        
        col_1 = np.array(col_1)
        col_2 = np.array(col_2)
        data = np.column_stack((col_1, col_2))
        data = data.astype(dtype=np.float16)

        no_columns = data.shape[1]
        col_names = ['Series_' + str(i + 1) for i in range(no_columns)]
        
        df = pd.DataFrame(data=data, columns=col_names)  # df of reverse symmetric integers
        arr_neut = cross_neutral(df, 'median', sequential=True)
        col_dif = np.subtract(arr_neut[:, 1], arr_neut[:, 0])

        input_ = np.array(input_, dtype = np.float16)
        input_rev = input_[::-1] ## Reverse the input using slicing.

        self.assertTrue(np.all(col_dif == input_rev))

        col1 = np.linspace(1, 21, 21, dtype=np.float16)
        shuffle(col_1)
        col2 = col1 * 10
        stack_col = np.column_stack((col1, col2))
        df = pd.DataFrame(data = stack_col, columns=['Series_1', 'Series_2'])
        
        arr_neutral = cross_neutral(df, neutral='mean', sequential=False)
        self.assertTrue(np.all(arr_neutral[:, 0] == 11.0))
        self.assertTrue(np.all(arr_neutral[:, 0] == arr_neutral[:, 1] / 10))

    def test_nan_insert(self):

        # Todo: short code testing first non-NA with or without min_obs across columns: Series.first_valid_index()

        arr_d = np.zeros((40, 4), dtype=object)
        
        data = np.linspace(1, 40, 40, dtype=np.float32)
        shuffle(data)
        data = data.reshape((8, 5))
        data[0:3, 2] = np.nan
        data[0, 0] = np.nan
        data[0:4, 4] = np.nan
        
        arr_d[:, 3] = np.ravel(data, order = 'F')
        extend_cids = ['AUD', 'CAD', 'FRA', 'GBP', 'USD']
        arr_d[:, 0] = np.array(sorted(extend_cids * 8))

        arr_d[:, 1] = np.repeat('XR', 40)
        dates = pd.date_range(start="2020-01-01", periods=8, freq='d')
        arr_d[:, 2] = np.array(list(dates) * 5)
        contrived_df = pd.DataFrame(data = arr_d, columns = ['cid', 'xcat', 'real_date', 'value'])
        dfw = contrived_df.pivot(index = 'real_date', columns = 'cid', values = 'value')  # example dataframe

        min_obs = 3
        dfw_zns = nan_insert(dfw, min_obs)  # test dataframe

        df_copy = dfw.copy()
        nan_arr = np.isnan(data)
        indices = np.where(nan_arr == False)
        indices_d = tuple(zip(indices[1], indices[0]))
        indices_dict = defaultdict(list)
        for tup in indices_d:
            indices_dict[tup[0]].append(tup[1])

        for k, v in indices_dict.items():
            df_copy.iloc[:, k][v[0]:(v[0] + min_obs)] = np.nan

        test = (df_copy.fillna(0) == dfw_zns.fillna(0)).to_numpy()
        self.assertTrue(np.all(test))
        

    def test_zn_scores(self):

        # Todo: focus on checking correct values by calling function with dfd and focusing on a few values
        # Todo: Also test that pan_weight and thresh are producing correct results.

        ## Using the globally defined DataFrame.
        with self.assertRaises(AssertionError):
            df = make_zn_scores(dfd, 'XR', cids, sequential=False, neutral='std',
                                thresh=1.5, postfix='ZN')  # test catching neutral value error
        with self.assertRaises(AssertionError):
            df = make_zn_scores(dfd, 'XR', cids, sequential=False, neutral='std', thresh=0.5,
                                pan_weight=1.0, postfix='ZN')  # test catching non-valid thresh value

        with self.assertRaises(AssertionError):
            df = make_zn_scores(dfd, 'XR', cids, sequential=False, pan_weight=1.2)  # test catching panel weight

        ## Test the Zn_Score, with a Panel Weighting of one, using the Mean for the neutral parameter.
        val = randint(1, 39)
        data = np.linspace(-val, val, (val * 2) + 1, dtype=np.float16)
        mean = sum(data) / len(data)
        col1 = data[-val:]
        col2 = data[:val]
        col2 = col2[::-1] ## Reverse the data series to reflect the linear, negative correlation.
        data = np.concatenate((col1, col2))
        ## The two series are uniformally distributed around the panel mean.
        ## Therefore, the evolving standard deviation will grow at a constant rate, 0.5 increment, to reflect the negative linear correlation between the two return series.

        data_col = np.column_stack((col1, col2))

        arr_d = np.zeros((len(data), 4), dtype = object)
        arr_d[:, 3] = data

        aud = np.repeat('AUD', len(col1))
        cad = np.repeat('CAD', len(col1))
        arr_d[:, 0] = np.concatenate((aud, cad))
        dates = pd.date_range(start = "2020-01-01", periods = len(data) / 2, freq = 'd')
        arr_d[:, 2] = np.array(list(dates) * 2)
        arr_d[:, 1] = np.repeat('XR', len(data))

        ## The panel mean will equal zero.
        ## The Standard Deviation Array will be a one-dimensional Array given the statistic is computed across all cross-sections.
        end = (len(col1) / 2) + 0.5
        std = np.linspace(1, end, len(col1)) ## f(x) = y.
        std = std[:, np.newaxis]
        
        rational = np.divide((data_col - mean), std)

        cids_ = ['AUD', 'CAD']
        contrived_df = pd.DataFrame(data = arr_d, columns = ['cid', 'xcat', 'real_date', 'value'])

        df = make_zn_scores(contrived_df, 'XR', cids_, sequential = False, min_obs = 0, neutral = 'mean',
                            pan_weight = 1.0)

        check_val = np.concatenate((rational[:, 0], rational[:, 1]))
        zn_score_algo = df['value'].to_numpy()
        self.assertTrue(np.all(check_val == zn_score_algo))  # test for correct values
        

if __name__ == '__main__':

    unittest.main()
