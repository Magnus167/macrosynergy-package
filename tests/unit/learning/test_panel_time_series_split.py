from typing import List
import unittest
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.neighbors import KNeighborsRegressor
from sklearn.model_selection import cross_val_score
from parameterized import parameterized

from macrosynergy.learning import (
    IntervalPanelSplit,
    ForwardPanelSplit,
    KFoldPanelSplit,
)


class TestAll(unittest.TestCase):
    def setUp(self):
        cids = ["AUD", "CAD", "GBP", "USD"]
        xcats = ["XR", "CPI", "GROWTH", "RIR"]

        df_cids = pd.DataFrame(index=cids, columns=["earliest", "latest"])
        df_cids.loc["AUD"] = ["2002-01-01", "2020-12-31"]
        df_cids.loc["CAD"] = ["2003-01-01", "2020-12-31"]
        df_cids.loc["GBP"] = ["2000-01-01", "2020-12-31"]
        df_cids.loc["USD"] = ["2000-01-01", "2020-12-31"]

        tuples = []

        for cid in cids:
            # get list of all elidgible dates
            sdate = df_cids.loc[cid]["earliest"]
            edate = df_cids.loc[cid]["latest"]
            all_days = pd.date_range(sdate, edate)
            work_days = all_days[all_days.weekday < 5]
            for work_day in work_days:
                tuples.append((cid, work_day))

        n_samples = len(tuples)
        ftrs = np.random.normal(loc=0, scale=1, size=(n_samples, 3))
        labels = np.matmul(ftrs, [1, 2, -1]) + np.random.normal(0, 0.5, len(ftrs))
        df = pd.DataFrame(
            data=np.concatenate((np.reshape(labels, (-1, 1)), ftrs), axis=1),
            index=pd.MultiIndex.from_tuples(tuples, names=["cid", "real_date"]),
            columns=xcats,
            dtype=np.float32,
        )

        self.X = df.drop(columns="XR")
        self.y = df["XR"]

    # def test_crossval_application(self):
    #     # Given a generated panel with a true linear relationship between features and target,
    #     # test that the cross validation procedure correctly identifies that a linear regression
    #     # is more suitable than a 1-nearest neighbor model.
    #     # self.setUp()

    #     # models
    #     lr = LinearRegression()
    #     knn = KNeighborsRegressor(n_neighbors=1)
    #     splitter = IntervalPanelSplit(
    #         train_intervals=1, min_cids=2, min_periods=21 * 12, test_size=1
    #     )
    #     lrsplits = cross_val_score(
    #         lr,
    #         self.X,
    #         self.y,
    #         scoring="neg_root_mean_squared_error",
    #         cv=splitter,
    #         n_jobs=-1,
    #     )
    #     knnsplits = cross_val_score(
    #         knn,
    #         self.X,
    #         self.y,
    #         scoring="neg_root_mean_squared_error",
    #         cv=splitter,
    #         n_jobs=-1,
    #     )

    #     self.assertLess(np.mean(-lrsplits), np.mean(-knnsplits))

    @parameterized.expand([2, 4, 8])
    def test_forward_n_splits(self, n_splits):
        splitter = ForwardPanelSplit(n_splits=n_splits)
        splits = list(splitter.split(self.X, self.y))
        self.assertEqual(len(splits), n_splits)

    @parameterized.expand([2, 4, 8])
    def test_kfold_n_splits(self, n_splits):
        splitter = KFoldPanelSplit(n_splits=n_splits)
        splits = list(splitter.split(self.X, self.y))
        self.assertEqual(len(splits), n_splits)

    def test_forward_n_splits_too_small(self):
        with self.assertRaises(ValueError):
            ForwardPanelSplit(n_splits=1)

    def test_kfold_n_splits_too_small(self):
        with self.assertRaises(ValueError):
            KFoldPanelSplit(n_splits=1)

    def test_forward_split(self):
        periods1 = 6
        periods2 = 6
        n_splits = 5
        X, y = self.make_simple_df(periods1=periods1, periods2=periods2)
        splitter = ForwardPanelSplit(n_splits=n_splits)
        splits = list(splitter.split(X, y))
        for i in range(n_splits):
            # Training sets for each cid
            self.assertEqual(splits[i][0][i], i)
            self.assertEqual(splits[i][0][i * 2 + 1], i + periods1)

            # Test sets for each cid
            self.assertEqual(splits[i][1][0], i + 1)
            self.assertEqual(splits[i][1][1], i + periods1 + 1)

    def test_kfold_split(self):
        periods1 = 5
        periods2 = 5
        n_splits = 5
        X, y = self.make_simple_df(periods1=periods1, periods2=periods2)
        indices = np.arange(X.shape[0])
        splitter = KFoldPanelSplit(n_splits=n_splits)
        splits = list(splitter.split(X, y))
        for i in range(n_splits):
            # Test sets for each cid
            self.assertEqual(splits[i][1][0], i)
            self.assertEqual(splits[i][1][1], i + periods1)

            test_set = splits[i][1]
            train_set = splits[i][0]

            # assert train set is indices excluding test set
            self.assertTrue(np.array_equal(np.setdiff1d(indices, test_set), train_set))

    def make_simple_df(
        self,
        start1="2020-01-01",
        start2="2020-01-01",
        periods1=10,
        periods2=10,
        freq1="D",
        freq2="D",
    ):
        dates_cid1 = pd.date_range(start=start1, periods=periods1, freq=freq1)
        dates_cid2 = pd.date_range(start=start2, periods=periods2, freq=freq2)

        # Create a MultiIndex for each cid with the respective dates
        multiindex_cid1 = pd.MultiIndex.from_product(
            [["cid1"], dates_cid1], names=["cid", "real_date"]
        )
        multiindex_cid2 = pd.MultiIndex.from_product(
            [["cid2"], dates_cid2], names=["cid", "real_date"]
        )

        # Concatenate the MultiIndexes
        multiindex = multiindex_cid1.append(multiindex_cid2)

        # Initialize a DataFrame with the MultiIndex and columns xcat1 and xcat2
        # and random data.
        df = pd.DataFrame(
            np.random.rand(len(multiindex), 2),
            index=multiindex,
            columns=["xcat1", "xcat2"],
        )

        X = df.drop(columns=["xcat2"])
        y = df["xcat2"]

        return X, y


if __name__ == "__main__":
    unittest.main()

    # test = TestAll()
    # X, y = test.make_simple_df(periods1=5, periods2=5)
    # splitter = KFoldPanelSplit(n_splits=5)
    # splits = list(splitter.split(X, y))
    # print(splits)
    # splitter.visualise_splits(X, y)
