import numpy as np
import pandas as pd
from typing import List, Union, Tuple
import time
from collections import defaultdict
from itertools import islice
from bisect import insort
from macrosynergy.management.simulate_quantamental_data import make_qdf


class RollingMedian(object):
    '''Slow running-median with O(n) updates, because of List's unavoidable shifting, where n is the window size.'''

    def __init__(self, iterable):
        self.it = iter(iterable)
        self.list = list(islice(self.it, 1))
        self.sortedlist = sorted(self.list)

    @staticmethod
    def isOdd(num):

        return (num & 1)

    def __iter__(self):
        
        list_ = self.list
        sortedlist = self.sortedlist
        length = len(list_)
        midpoint = length // 2
        yield sortedlist[midpoint]

        for newelem in self.it:
            length += 1
            midpoint = length // 2
            ## Utilising the Bisect package to avoid a superfluous reordering, of the data structure, through each iteration: O(log(n)) instead of O(n(log(n))) if naive implementation used.
            insort(sortedlist, newelem)
            if not self.isOdd(length):
                sum_ = sortedlist[midpoint] + sortedlist[midpoint - 1]
                yield sum_ / 2 
            else:   
                yield sortedlist[midpoint]
                

## Broadcasting to convert a one element Array into an Array of n-length.
def dimension(arr, n):

    return np.lib.stride_tricks.as_strided(arr,
                                          shape = (n, ) + arr.shape,
                                          strides = (0, ) + arr.strides)

def rolling_std(v):

    def compute(mean, n):
        nonlocal v
        
        mean = np.array(mean)
        mean = dimension(mean, n)

        active_v = v[:n]
        numerator = np.sum((active_v - mean) ** 2)
        rational = numerator / n
        
        return np.sqrt(rational)

    return compute


def z_rolling(lists, neutral, min_obs):

    def compute(arr):

        arr = arr[:, 1]
        
        length = len(arr)
        assert length > min_obs
        
        days = np.linspace(1, length, length, dtype = int)
            
        ret = np.cumsum(arr)
        rolling_mean = ret / days
        
        if neutral == 'median':
            median_series = list(RollingMedian(arr))
            median_series = np.array(median_series)
            numerator = arr - median_series
        elif neutral == 'zero':
            zero_series = np.zeros(length)
            numerator = arr - zero_series
        else:
            numerator = arr - rolling_mean

        func = rolling_std(arr)
        vfunc = np.vectorize(func)
        std = vfunc(rolling_mean, days)

        z_scores = np.zeros(length)
        z_scores[1:] = np.divide(numerator[1:], std[1:])
        return np.column_stack((arr, z_scores))

    return list(map(compute, lists))

def merge(arr):

    return arr[:, 0]

def func(str_, int_):
    return [str_] * int_

def mult(xcats, list_):

    return list(map(func, xcats, list_))

class dfManipulation:

    def __init__(self, df, cids, xcat):
        self.dfd = dfd = df
        self.cids = cids
        self.xcats = xcat
        self.d_xcat = defaultdict(list)
        self.cid_xcat = {}

    @staticmethod
    def assertion(c_1, c_2):
        list_ = [c_1, c_2]
        list_ = sorted(list_)
        if list_ != ['cids', 'xcats']:
            raise AssertionError("Incorrect strings passed.")

    def fields_iter(self, category, category_2):
        self.assertion(category, category_2)
        column = category[:-1]
        
        attribute = 'self.' + category
        attribute_2 = 'self.' + category_2
        self.__dict__['interior'] = attribute_2
        
        for field in eval(attribute):
            self.__dict__['exterior'] = field
            self.__dict__['df_temp'] = dfd[dfd[column] == field]
            self.cid_xcat[field] = list(map(self.filt_xcat, eval(attribute_2)))

    def df_reduce(self, column, field):
        df_ = self.df_temp[self.df_temp[column] == field]
        return df_
                           
    def filt_xcat(self, field):
        
        column = self.interior.split('.')
        column = column[1][:-1]
        
        df_ = self.df_reduce(column, field)
        data = df_[['real_date', 'value']].to_numpy()
        self.d_xcat[self.exterior].append(len(data[:, 0]))
        
        return data

zero_counter = lambda row: (row == 0.0).sum()

def missing_handle(row):
    length = len(row)
    count = zero_counter(row)

    return (length - count)

## First Class Function: acts as a quasi-Class where the parameter acts as a field and is subsequently accessible inside all internal functions that define their own local scope.
def standard_dev(mean, i = -1):
    
    def compute(row):
        nonlocal mean, i
        i += 1
        mean_row = mean[i] 
        
        data = row[np.nonzero(row)]
        countries = len(data)
        numerator = (data - mean_row) ** 2
        numerator = np.sum(numerator)
        rational = numerator / countries
    
        return np.sqrt(rational)

    return compute

def ordering(df, arr):
    dict_ = df.to_dict()
    list_ = np.zeros(len(arr), dtype = object)
    
    for k, v in dict_.items():
        index_ = np.where(arr == v)
        index_ = int(index_[0][0])
        list_[index_] = k
    return list_


def z_formula(arr, neutral, std):
    neutral = neutral[:, np.newaxis]
    std = std[:, np.newaxis]
    
    diff = np.subtract(arr, neutral)
    z_data = np.divide(diff, std)

    return z_data        

def cross_section(dfd: pd.DataFrame, cids: List[str] = None, min_obs: int = 252,
                  neutral: str = 'zero', xcat: str = None):

    df_output = pd.DataFrame(data = None, columns = ['Timestamp', 'cid', 'xcat', 'Z-Score'])
        
    df_temp = dfd[dfd['xcat'] == xcat]
    df_pivot = df_temp.pivot(index = 'real_date', columns = 'cid', values = 'value')
    arr = df_pivot[cids].values
    dates = df_pivot.index.to_numpy()
    
    data = np.nan_to_num(arr, copy = True)
    act_countr = (data != 0.0).sum(axis = 1)
    index = np.argmax(act_countr == len(df_pivot.columns))
    columns_ = ordering(df_pivot.iloc[index], arr[index, :])
    columns_ax = columns_[:, np.newaxis]
    
    if not np.all(act_countr > 1):
        index_ = np.where(act_countr != 1)[0]
        data = np.take(data, index_, axis = 0)
        arr = np.take(arr, index_, axis = 0)
        act_countr = np.take(act_countr, index_)
        dates = np.take(dates, index_)

    l_dates = len(dates)
    cids_arr = np.repeat(columns_ax, l_dates, axis = 1)
    cids_arr = cids_arr.reshape((l_dates * len(columns_), ))

    mean_ = np.divide(np.sum(data, axis = 1), act_countr)
    func = standard_dev(mean_)
    std = np.apply_along_axis(func, axis = 1, arr = data)

    if neutral == 'mean':
        z_data = z_formula(arr, mean_, std)
    elif neutral == 'median':
        median = np.nanmedian(arr, axis = 1)
        z_data = z_formula(arr, median, std)
    else:
        zero = np.zeros((l_dates, ))
        z_data = z_formula(arr, zero, std)
            
    dates = dimension(dates, len(df_pivot.columns))
    dates = dates.ravel()
    z_dimension = z_data.shape[0] * z_data.shape[1]
    z_data = z_data.T
    z_data = z_data.reshape((z_dimension))

    df_output['Timestamp'] = dates
    df_output['cid'] = cids_arr
    df_output['xcat'] = xcat
    df_output['z_score'] = z_data

    return df_output
            

def out_sample(dfd: pd.DataFrame, cids: List[str] = None, min_obs: int = 252,
               neutral: str = 'zero', xcat: str = None):

    cid_xcat_cl = {}
    cid_z = {}

    df_inst = dfManipulation(dfd, cids, xcat)
    df_inst.fields_iter('cids', 'xcats')
    cid_xcat_cl = df_inst.cid_xcat
    d_xcat = df_inst.d_xcat

    for cid in cids:
        cid_z[cid] = z_rolling(cid_xcat_cl[cid], neutral, min_obs)

    stat = 'z_score_' + neutral
    qdf_cols = ['cid', 'xcat', 'real_date', 'value', stat]
    df_lists = []
    
    for cid in cids:
        df_out = pd.DataFrame(columns = qdf_cols)
        df_out['xcat'] = np.concatenate(mult(xcat, d_xcat[cid]))
        list_ = tuple(map(merge, cid_xcat_cl[cid]))
        df_out['real_date'] = np.concatenate(list_)
        df_out[['value', stat]] = np.concatenate(cid_z[cid])
        df_out['cid'] = cid
        df_lists.append(df_out)

    final_df = pd.concat(df_lists, ignore_index = True)
    return final_df


def zn_score(dfd: pd.DataFrame, cids: List[str] = None, xcats: List[str] = None,
             oos: bool = False, min_obs: int = 252, cross: bool = False,
             neutral: str = 'zero', abs_max: float = None, weighting: bool = False,
             c_weight: float = 0.5, xcat: str = None):
    
    assert xcat in xcats
    assert neutral in ['median', 'zero', 'mean']
    
    if weighting:
        assert c_weight < 1.0 and c_weight > 0.0

    if not weighting:
        if oos:
            xcat = [xcat]
            final_df = out_sample(dfd, cids = cids,
                                  neutral = neutral, xcat = xcat)
        else:
            final_df = cross_section(dfd, cids = cids,
                                     neutral = neutral, xcat = xcat)
    else:
        final_df = pd.DataFrame(data = None, columns =
                                ['Timestamp', 'cid', 'xcat', 'z_score_time', 'z_cross', 'Weighted'])
        xcat_ = [xcat]
        time_df = out_sample(dfd, cids = cids, neutral = neutral, xcat = xcat_)
        cross_df = cross_section(dfd, cids = cids, neutral = neutral, xcat = xcat)

        final_df['Timestamp'] = time_df['real_date']
        final_df['cid'] = time_df['cid']
        final_df['xcat'] = xcat
        final_df['z_score_time'] = time_df['value']
        final_df['z_cross'] = cross_df['z_score']
        weight = (cross_df['z_score'] * c_weight) + ((1 - c_weight) * time_df['value'])
        final_df['Weighted'] = weight
        
    return final_df

        

if __name__ == "__main__":
    ## Country IDs.
    cids = ['AUD', 'CAD', 'GBP', 'USD', 'NZD']
    ## Macroeconomic Fields: GDP, Inflation
    xcats = ['XR', 'CRY', 'GROWTH', 'INFL']

    df_cids = pd.DataFrame(index = cids, columns = ['earliest', 'latest', 'mean_add', 'sd_mult'])

    df_cids.loc['AUD'] = ['2010-01-01', '2020-12-31', 0.5, 2]
    df_cids.loc['CAD'] = ['2011-01-01', '2020-11-30', 0, 1]
    df_cids.loc['GBP'] = ['2012-01-01', '2020-10-30', -0.2, 0.5]
    df_cids.loc['USD'] = ['2013-01-01', '2020-09-30', -0.2, 0.5]
    df_cids.loc['NZD'] = ['2002-01-01', '2020-09-30', -0.1, 2]

    df_xcats = pd.DataFrame(index = xcats, columns = ['earliest', 'latest', 'mean_add', 'sd_mult', 'ar_coef', 'back_coef'])
    df_xcats.loc['XR'] = ['2010-01-01', '2020-12-31', 0, 1, 0, 0.3]
    df_xcats.loc['CRY'] = ['2011-01-01', '2020-10-30', 1, 2, 0.9, 0.5]
    df_xcats.loc['GROWTH'] = ['2012-01-01', '2020-10-30', 1, 2, 0.9, 1]
    df_xcats.loc['INFL'] = ['2013-01-01', '2020-10-30', 1, 2, 0.8, 0.5]
    
    print("Uses Ralph's make_qdf() function.")
    start = time.time()
    dfd = make_qdf(df_cids, df_xcats, back_ar = 0.75)
    print(f"Time Elapsed: {time.time() - start}.")

    ## df = zn_score(dfd, cids = fields_cids, xcats = fields_cats, oos = True, neutral = 'median', xcat = 'CRY')

    start = time.time()
    df = zn_score(dfd, cids = cids, xcats = xcats, oos = False, cross = True,
                  neutral = 'median', weighting = True, c_weight = 0.85, xcat = 'CRY')
    print(f"Time Elapsed: {time.time() - start}.")
    print(df)