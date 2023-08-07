import inspect
import logging
import warnings
from functools import wraps
import itertools
from types import ModuleType
from typing import (
    Callable,
    Dict,
    Any,
    Union,
    Tuple,
    List,
    Dict,
    Optional,
    Type,
    get_origin,
    get_args,
)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from macrosynergy.management import reduce_df, reduce_df_by_ticker
from macrosynergy.management.utils import standardise_dataframe

logger = logging.getLogger(__name__)
NoneType = type(None)


def is_matching_subscripted_type(value: Any, type_hint: Type[Any]) -> bool:
    origin = get_origin(type_hint)
    args = get_args(type_hint)

    # handling lists
    if origin in [list, List]:
        if not isinstance(value, list):
            return False
        return all(isinstance(item, args[0]) for item in value)

    # tuples
    if origin in [tuple, Tuple]:
        if not isinstance(value, tuple) or len(value) != len(args):
            return False
        return all(isinstance(item, expected) for item, expected in zip(value, args))

    # dicts
    if origin in [dict, Dict]:
        if not isinstance(value, dict):
            return False
        key_type, value_type = args
        return all(
            isinstance(k, key_type) and isinstance(v, value_type)
            for k, v in value.items()
        )

    # unions and optionals
    if origin is Union:
        for possible_type in args:
            if get_origin(possible_type):  # is subscripted
                if is_matching_subscripted_type(value, possible_type):
                    return True
            elif isinstance(value, possible_type):
                return True
        return False

    return False


def _get_expected(arg_type_hint: Type[Any]) -> List[str]:
    """
    Based on the type hint, return a list of strings that represent
    the type hint - including any nested type hints.
    """
    origin = get_origin(arg_type_hint)
    args = get_args(arg_type_hint)

    # handling lists
    if origin in [list, List]:
        return [f"List[{_get_expected(args[0])[0]}]"]

    # tuples
    if origin in [tuple, Tuple]:
        return [f"Tuple[{', '.join(_get_expected(arg) for arg in args)}]"]

    # dicts
    if origin in [dict, Dict]:
        return [f"Dict[{', '.join(_get_expected(arg) for arg in args)}]"]

    # unions and optionals
    if origin in [Union, Optional]:
        # get a flat list of all the expected types
        expected_types: List[str] = []
        for possible_type in args:
            if get_origin(possible_type):
                expected_types.extend(_get_expected(possible_type))
            else:
                expected_types.append(str(possible_type))
        return expected_types

    return [str(arg_type_hint)]


def argvalidation(func: Callable[..., Any]) -> Callable[..., Any]:
    def format_expected_type(expected_types: List[Any]) -> str:
        # format the expected types to read nicely, and to remove 'typing.' from the string
        if isinstance(expected_types, tuple):
            expected_types = list(expected_types)
        for i, et in enumerate(expected_types):
            if str(et).startswith("typing."):
                expected_types[i] = str(et).replace("typing.", "")
            if et is NoneType:
                expected_types[i] = "None"

        if len(expected_types) == 1:
            return f"`{expected_types[0]}`"
        elif len(expected_types) == 2:
            return f"`{expected_types[0]}` or `{expected_types[1]}`"
        else:
            return f"{', '.join([f'`{t}`' for t in expected_types[:-1]])}, or `{expected_types[-1]}`"

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        func_sig: inspect.Signature = inspect.signature(func)
        func_params: Dict[str, inspect.Parameter] = func_sig.parameters
        func_annotations: Dict[str, Any] = func_sig.return_annotation
        func_args: Dict[str, Any] = inspect.getcallargs(func, *args, **kwargs)

        # validate the arguments
        for arg_name, arg_value in func_args.items():
            if arg_name in func_params:
                arg_type: Type[Any] = func_params[arg_name].annotation
                if arg_type is not inspect._empty:
                    origin = get_origin(arg_type)
                    if origin:  # Handling subscripted types
                        if not is_matching_subscripted_type(arg_value, arg_type):
                            exp_types: str = format_expected_type(get_args(arg_type))
                            raise TypeError(
                                f"Argument `{arg_name}` must be of type {exp_types}, "
                                f"not `{type(arg_value).__name__}` (with value `{arg_value}`)."
                            )
                    else:  # For simple, non-generic types
                        if not isinstance(arg_value, arg_type):
                            raise TypeError(
                                f"Argument `{arg_name}` must be of type `{arg_type}`, "
                                f"not `{type(arg_value).__name__}` (with value `{arg_value}`)."
                            )

        # validate the return value
        return_value: Any = func(*args, **kwargs)
        if func_annotations is not inspect._empty:
            if not isinstance(return_value, func_annotations):
                warnings.warn(
                    f"Return value of `{func.__name__}` is not of type "
                    f"`{func_annotations}`, but of type `{type(return_value)}`."
                )

        return return_value

    return wrapper


def argcopy(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        copy_types = (
            list,
            dict,
            pd.DataFrame,
            np.ndarray,
            pd.Series,
            pd.Index,
            pd.MultiIndex,
            set,
            tuple,
        )
        new_args: List[Tuple[Any, ...]] = []
        for arg in args:
            if isinstance(arg, copy_types) or issubclass(type(arg), copy_types):
                new_args.append(arg.copy())
            else:
                new_args.append(arg)
        new_kwargs: Dict[str, Any] = {}
        for key, value in kwargs.items():
            if isinstance(value, copy_types) or issubclass(type(value), copy_types):
                new_kwargs[key] = value.copy()
            else:
                new_kwargs[key] = value

        return func(*new_args, **new_kwargs)

    return wrapper


class PlotterMetaClass(type):
    def __init__(cls, name, bases, dct: Dict[str, Any]):
        super().__init__(name, bases, dct)
        for attr_name, attr_value in dct.items():
            if callable(attr_value):
                setattr(cls, attr_name, argcopy(argvalidation(attr_value)))


class Plotter(metaclass=PlotterMetaClass):
    """
    Base class for a DataFrame Plotter.
    It provides a shared interface for the plotter classes,
    and some common functionality - currently just the filtering
    of the DataFrame.

    Parameters
    :param <pd.DataFrame> df: A DataFrame with the following columns:
        'cid', 'xcat', 'real_date', and at least one metric from -
        'value', 'grading', 'eop_lag', or 'mop_lag'.
    :param <List[str]> cids: A list of cids to select from the DataFrame
        (self.df). If None, all cids are selected.
    :param <List[str]> xcats: A list of xcats to select from the DataFrame
        (self.df). If None, all xcats are selected.F
    :param <List[str]> metrics: A list of metrics to select from the DataFrame
        (self.df). If None, all metrics are selected.
    :param <str> start_date: ISO-8601 formatted date. Select data from
        this date onwards. If None, all dates are selected.
    :param <str> end_date: ISO-8601 formatted date. Select data up to
        and including this date. If None, all dates are selected.
    :param <str> backend: The plotting backend to use. Currently only
        'matplotlib' and 'seaborn' are supported, with 'matplotlib' as
        the default.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        cids: Optional[List[str]] = None,
        xcats: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        intersect: Optional[bool] = False,
        tickers: Optional[List[str]] = None,
        blacklist: Optional[Dict[str, List[str]]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        backend: Optional[str] = "matplotlib",
    ):
        sdf: pd.DataFrame = df.copy()
        df_cols: List[str] = ["real_date", "cid", "xcat"]
        if metrics is None:
            metrics: List[str] = list(set(sdf.columns) - set(df_cols))

        df_cols += metrics
        sdf = standardise_dataframe(df=sdf)
        if not set(df_cols).issubset(set(sdf.columns)):
            raise ValueError(f"DataFrame must contain the following columns: {df_cols}")

        if cids is None:
            cids = list(sdf["cid"].unique())
        if xcats is None:
            xcats = list(sdf["xcat"].unique())

        if start is None:
            start: str = pd.Timestamp(sdf["real_date"].min()).strftime("%Y-%m-%d")
        if end is None:
            end: str = pd.Timestamp(sdf["real_date"].max()).strftime("%Y-%m-%d")

        if tickers is not None:
            sdf = reduce_df_by_ticker(
                df=sdf,
                tickers=tickers,
            )

        sdf: pd.DataFrame
        cids: List[str]
        xcats: List[str]
        sdf, xcats, cids = reduce_df(
            df=sdf,
            cids=cids if isinstance(cids, list) else [cids],
            xcats=xcats if isinstance(xcats, list) else [xcats],
            intersect=intersect,
            start=start,
            end=end,
            blacklist=blacklist,
            out_all=True,
        )
        # if the DataFrame is empty, raise an error
        if sdf.empty:
            raise ValueError(
                "The arguments provided resulted in an "
                "empty DataFrame when filtered (see `reduce_df`)."
            )

        self.df: pd.DataFrame = sdf
        self.cids: List[str] = cids
        self.xcats: List[str] = xcats
        self.metrics: List[str] = metrics
        self.intersect: bool = intersect
        self.tickers: List[str] = tickers
        self.blacklist: Dict[str, List[str]] = blacklist
        self.start: str = start
        self.end: str = end

        self.backend: ModuleType
        if backend.startswith("m"):
            self.backend = plt
            self.backend.style.use("seaborn-v0_8-darkgrid")
        elif backend.startswith("s"):
            self.backend = sns
            self.backend.set_style("darkgrid")

        else:
            raise NotImplementedError(f"Backend `{backend}` is not supported.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass
