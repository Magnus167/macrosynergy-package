import unittest
from macrosynergy.signal.signal_return import SignalsReturns

from tests.simulate import make_qdf
from sklearn.metrics import accuracy_score, precision_score
from scipy import stats
import random
import pandas as pd
import numpy as np
from typing import List, Dict


class TestAll(unittest.TestCase):
    def dataframe_generator(self):
        """
        Create a standardised DataFrame defined over the three categories.
        """

        self.cids: List[str] = ["AUD", "CAD", "GBP", "NZD", "USD"]
        self.xcats: List[str] = ["XR", "CRY", "GROWTH", "INFL"]

        df_cids = pd.DataFrame(
            index=self.cids, columns=["earliest", "latest", "mean_add", "sd_mult"]
        )

        # Purposefully choose a different start date for all cross-sections. Used to test
        # communal sampling.
        df_cids.loc["AUD"] = ["2011-01-01", "2020-12-31", 0, 1]
        df_cids.loc["CAD"] = ["2009-01-01", "2020-10-30", 0, 2]
        df_cids.loc["GBP"] = ["2010-01-01", "2020-08-30", 0, 5]
        df_cids.loc["NZD"] = ["2008-01-01", "2020-06-30", 0, 3]
        df_cids.loc["USD"] = ["2012-01-01", "2020-12-31", 0, 4]

        df_xcats = pd.DataFrame(
            index=self.xcats,
            columns=[
                "earliest",
                "latest",
                "mean_add",
                "sd_mult",
                "ar_coef",
                "back_coef",
            ],
        )

        df_xcats.loc["XR"] = ["2000-01-01", "2020-12-31", 0.1, 1, 0, 0.3]
        df_xcats.loc["CRY"] = ["2000-01-01", "2020-10-30", 0, 2, 0.95, 1]
        df_xcats.loc["GROWTH"] = ["2001-01-01", "2020-10-30", 0, 2, 0.9, 1]
        df_xcats.loc["INFL"] = ["2001-01-01", "2020-10-30", 0, 2, 0.8, 0.5]

        random.seed(2)
        dfd = make_qdf(df_cids, df_xcats, back_ar=0.75)

        self.dfd: pd.DataFrame = dfd

        black = {
            "AUD": ["2000-01-01", "2003-12-31"],
            "GBP": ["2018-01-01", "2100-01-01"],
        }

        self.blacklist: Dict[str, List[str]] = black

        assert "dfd" in vars(self).keys(), (
            "Instantiation of DataFrame missing from " "field dictionary."
        )

    def test_constructor(self):
        self.dataframe_generator()
        # Test the Class's constructor.

        # First, test the assertions.
        # Testing that the dataframe is actually of type Pandas.DataFrame
        with self.assertRaises(TypeError):
            sr = SignalsReturns(
                df="STRING", rets="XR", sigs="CRY", freqs="D", blacklist=self.blacklist
            )
        # Testing that the dataframe has the correct columns
        with self.assertRaises(ValueError):
            sr = SignalsReturns(
                df=pd.DataFrame(index=["FAIL"], columns=["FAIL"]),
                rets="XR",
                sigs="CRY",
                freqs="D",
                blacklist=self.blacklist,
            )
        print(self.dfd)
        # Test to confirm the primary signal must be present in the passed Dataframe
        with self.assertRaises(AssertionError):
            sr = SignalsReturns(
                df=self.dfd,
                rets="XR",
                sigs="MISSING",
                freqs="D",
                blacklist=self.blacklist,
            )
        # Test to confirm the primary signal must be present in the passed Dataframe
        with self.assertRaises(AssertionError):
            sr = SignalsReturns(
                df=self.dfd,
                rets="MISSING",
                sigs="CRY",
                freqs="D",
                blacklist=self.blacklist,
            )
        # Test to ensure that freqs is a specified string or list of strings
        with self.assertRaises(ValueError):
            sr = SignalsReturns(
                df=self.dfd,
                rets="XR",
                sigs="CRY",
                freqs="X",
                blacklist=self.blacklist,
            )
        # Test that cosp is set to a boolean value
        with self.assertRaises(TypeError):
            sr = SignalsReturns(
                df=self.dfd,
                rets="XR",
                sigs="CRY",
                freqs="D",
                cosp="FAIL",
                blacklist=self.blacklist,
            )
        # Test that Signals Returns can take in lists as arguments
        self.assertTrue(
            SignalsReturns(
                df=self.dfd,
                rets=["XR", "GROWTH"],
                sigs=["CRY", "INFL"],
                freqs=["Q", "M"],
                signs=[1, 1],
                agg_sigs=["last", "mean"],
                blacklist=self.blacklist,
            )
        )

    def test_single_relation_table(self):
        self.dataframe_generator()

        sr = SignalsReturns(
            df=self.dfd,
            rets="XR",
            sigs="CRY",
            freqs="Q",
            blacklist=self.blacklist,
            slip=1,
        )

        sr_no_slip = SignalsReturns(
            df=self.dfd,
            rets="XR",
            sigs="CRY",
            freqs="Q",
            blacklist=self.blacklist,
            slip=0,
        )

        # Test that each argument must be of the correct type
        with self.assertRaises(TypeError):
            sr.single_relation_table(ret=2)

        with self.assertRaises(TypeError):
            sr.single_relation_table(sig=2)

        with self.assertRaises(TypeError):
            sr.single_relation_table(freq=2)

        with self.assertRaises(TypeError):
            sr.single_relation_table(agg_sigs=2)

        sr.single_relation_table()
        sr_no_slip.single_relation_table()

        # Test that dataframe has been reduced to just the relevant columns and has
        # applied slippage

        self.assertTrue(set(sr.dfd["xcat"]) == set(["XR", "CRY"]))

        self.assertTrue(sr.dfd["value"][0] != sr.df["value"][0])

        self.assertTrue(sr_no_slip.dfd["value"][0] == sr_no_slip.df["value"][0])

        # Test Negative signs are correctly handled

        with self.assertRaises(TypeError):
            sr = SignalsReturns(
                df=self.dfd,
                rets="XR",
                sigs="CRY",
                freqs="Q",
                signs=["FAIL"],
                blacklist=self.blacklist,
                slip=1,
            )

        # Ensure that the signs doesn't have a longer length than the number of signals
        with self.assertRaises(ValueError):
            sr = SignalsReturns(
                df=self.dfd,
                rets="XR",
                sigs="CRY",
                freqs="Q",
                signs=[-1, -1],
                blacklist=self.blacklist,
                slip=1,
            )

        # Test table outputted is correct

    def test_multiple_relation_table(self):
        self.dataframe_generator()

        num_of_acc_cols = 10

        sr = SignalsReturns(
            df=self.dfd,
            rets="XR",
            sigs="CRY",
            freqs="Q",
            agg_sigs="last",
            blacklist=self.blacklist,
            slip=1,
        )

        self.assertTrue(sr.multiple_relations_table().shape == (1, num_of_acc_cols))

        sr = SignalsReturns(
            df=self.dfd,
            rets=["XR", "GROWTH"],
            sigs=["CRY", "INFL"],
            freqs=["Q", "M"],
            signs=[1, 1],
            agg_sigs=["last", "mean"],
            blacklist=self.blacklist,
        )

        self.assertTrue(sr.multiple_relations_table().shape == (16, num_of_acc_cols))

        with self.assertRaises(ValueError):
            sr.multiple_relations_table(rets="TEST")

        with self.assertRaises(ValueError):
            sr.multiple_relations_table(xcats="TEST")

        with self.assertRaises(ValueError):
            sr.multiple_relations_table(freqs="TEST")

        with self.assertRaises(ValueError):
            sr.multiple_relations_table(agg_sigs="TEST")

        rets = ["XR", "GROWTH"]
        xcats = ["INFL"]
        freqs = ["Q", "M"]
        agg_sigs = ["mean"]
        mrt = sr.multiple_relations_table(
            rets=rets, xcats=xcats, freqs=freqs, agg_sigs=agg_sigs
        )
        self.assertTrue(mrt.shape == (4, num_of_acc_cols))

    def test_single_statistic_table(self):
        self.dataframe_generator()

        sr = SignalsReturns(
            df=self.dfd,
            rets="XR",
            sigs="CRY",
            freqs="Q",
            blacklist=self.blacklist,
            slip=1,
        )

        with self.assertRaises(KeyError):
            sr.single_statistic_table(stat="FAIL")

        with self.assertRaises(ValueError):
            sr.single_statistic_table(stat="accuracy", type="FAIL")

        with self.assertRaises(TypeError):
            sr.single_statistic_table(stat="accuracy", rows="FAIL")

        with self.assertRaises(TypeError):
            sr.single_statistic_table(stat="accuracy", columns="FAIL")

        with self.assertRaises(ValueError):
            sr.single_statistic_table(stat="accuracy", rows=["FAIL"])

        with self.assertRaises(ValueError):
            sr.single_statistic_table(stat="accuracy", columns=["FAIL"])

        # Test that table is correctly shaped

        self.assertTrue(sr.single_statistic_table(stat="accuracy").shape == (1, 1))

        sr = SignalsReturns(
            df=self.dfd,
            rets=["XR", "GROWTH"],
            sigs=["CRY", "INFL"],
            freqs=["Q", "M"],
            agg_sigs=["last", "mean"],
            blacklist=self.blacklist,
            slip=1,
        )

        self.assertTrue(sr.single_statistic_table(stat="accuracy").shape == (4, 4))

        # Test that the table is correctly shaped when rows and columns are specified

        self.assertTrue(
            sr.single_statistic_table(
                stat="accuracy", rows=["freq", "xcat", "ret"], columns=["agg_sigs"]
            ).shape
            == (8, 2)
        )

if __name__ == "__main__":
    unittest.main()
