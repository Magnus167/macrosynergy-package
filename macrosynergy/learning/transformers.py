"""
Collection of scikit-learn transformer classes.

**NOTE: This module is under development, and is not yet ready for production use.**
"""

import numpy as np
import pandas as pd

from sklearn.linear_model import Lasso
from sklearn.base import BaseEstimator, TransformerMixin

from statsmodels.tools.tools import add_constant
from statsmodels.regression.mixed_linear_model import MixedLM

class LassoSelectorTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, alpha):
        """
        Transformer class to use the Lasso as a feature selection algorithm.
        Given a hyper-parameter, alpha, the Lasso model is fit and 
        the non-zero coefficients are used to extract features from an input dataframe.
        """
        self.alpha = alpha

    def fit(self, X, y):
        """
        Fit method to fit a Lasso regression and obtain the selected features.
        """
        self.p = X.shape[-1]
        self.lasso = Lasso(alpha=self.alpha).fit(X, y)
        self.selected_ftr_idxs = [i for i in range(self.p) if self.lasso.coef_[i] != 0]

    def transform(self, X):
        """
        Transform method to return only the selected features of the dataframe.
        """
        return X.iloc[:,self.selected_ftr_idxs]
    
class MapSelectorTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, threshold):
        self.threshold = threshold

    def fit(self, X, y):
        # determine the ftrs that are significant
        self.ftrs = []
        cols = X.columns

        for col in cols:
            ftr = X[col]
            ftr = add_constant(ftr)
            groups = ftr.reset_index().real_date
            re = MixedLM(y,ftr,groups).fit(reml=False)
            pval = re.pvalues[1]
            if pval < self.threshold:
                self.ftrs.append(col)


    def transform(self, X):
        return X[self.ftrs]
    
if __name__ == "__main__":
    from macrosynergy.management import make_qdf
    import macrosynergy.management as msm

    cids = ["AUD", "CAD", "GBP", "USD"]
    xcats = ["XR", "CRY", "GROWTH", "INFL"]
    cols = ["earliest", "latest", "mean_add", "sd_mult", "ar_coef", "back_coef"]

    """Example 1: Unbalanced panel """

    df_cids2 = pd.DataFrame(
        index=cids, columns=["earliest", "latest", "mean_add", "sd_mult"]
    )
    df_cids2.loc["AUD"] = ["2002-01-01", "2020-12-31", 0, 1]
    df_cids2.loc["CAD"] = ["2003-01-01", "2020-12-31", 0, 1]
    df_cids2.loc["GBP"] = ["2000-01-01", "2020-12-31", 0, 1]
    df_cids2.loc["USD"] = ["2000-01-01", "2020-12-31", 0, 1]

    df_xcats2 = pd.DataFrame(index=xcats, columns=cols)
    df_xcats2.loc["XR"] = ["2000-01-01", "2020-12-31", 0.1, 1, 0, 0.3]
    df_xcats2.loc["CRY"] = ["2000-01-01", "2020-12-31", 1, 2, 0.95, 1]
    df_xcats2.loc["GROWTH"] = ["2000-01-01", "2020-12-31", 1, 2, 0.9, 1]
    df_xcats2.loc["INFL"] = ["2000-01-01", "2020-12-31", 1, 2, 0.8, 0.5]

    dfd2 = make_qdf(df_cids2, df_xcats2, back_ar=0.75)
    dfd2["grading"] = np.ones(dfd2.shape[0])
    black = {"GBP": ["2009-01-01", "2012-06-30"], "CAD": ["2018-01-01", "2100-01-01"]}
    dfd2 = msm.reduce_df(df=dfd2, cids=cids, xcats=xcats, blacklist=black)

    dfd2 = dfd2.pivot(index=["cid", "real_date"], columns="xcat", values="value")
    X2 = dfd2.drop(columns=["XR"])
    y2 = dfd2["XR"]

    selector = MapSelectorTransformer(0.05)
    selector.fit(X2, y2)
    print(selector.transform(X2).columns)

    selector = LassoSelectorTransformer(0.00001)
    selector.fit(X2, y2)
    print(selector.transform(X2).columns)