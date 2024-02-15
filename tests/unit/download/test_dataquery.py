from unittest import mock
import unittest
import pandas as pd
import datetime
import base64
import io
import warnings
import logging
from typing import List, Dict, Union, Any
import requests
import numpy as np

from macrosynergy.download.jpmaqs import (
    JPMaQSDownload,
    deconstruct_expression,
    construct_expressions,
    get_expression_from_qdf,
    get_expression_from_wide_df,
    timeseries_to_column,
    timeseries_to_qdf,
    concat_column_dfs,
    validate_downloaded_df,
)
from macrosynergy.download.dataquery import (
    DataQueryInterface,
    OAuth,
    CertAuth,
    request_wrapper,
    validate_response,
    validate_download_args,
)
from macrosynergy.download.dataquery import (
    OAUTH_BASE_URL,
    OAUTH_TOKEN_URL,
    HEARTBEAT_ENDPOINT,
    TIMESERIES_ENDPOINT,
    API_DELAY_PARAM,
    CERT_BASE_URL,
    CATALOGUE_ENDPOINT,
    JPMAQS_GROUP_ID,
)
from macrosynergy.download.exceptions import (
    AuthenticationError,
    HeartbeatError,
    InvalidResponseError,
    DownloadError,
    InvalidDataframeError,
    NoContentError,
)

from macrosynergy.management.types import QuantamentalDataFrame

from .mock_helpers import mock_jpmaqs_value, mock_request_wrapper, random_string


class TestRequestWrapper(unittest.TestCase):
    def mock_response(
        self,
        url: str,
        status_code: int = 200,
        headers: Dict[str, str] = None,
        text: str = None,
        content: bytes = None,
    ) -> requests.Response:
        mock_resp: requests.Response = requests.Response()
        mock_resp.status_code = status_code
        mock_resp.headers = headers or {}
        mock_resp._content = content
        mock_resp._text = text
        mock_resp.request = requests.Request("GET", url)
        return mock_resp

    def test_validate_response(self):
        # mock a response with 401. assert raises authentication error
        user_id: str = f"User_{random_string()}"
        with self.assertRaises(AuthenticationError):
            validate_response(
                self.mock_response(url=OAUTH_TOKEN_URL, status_code=401),
                user_id=user_id,
            )

        # mock with a 403, and use url=oauth+heartbeat. assert raises heartbeat error
        with self.assertRaises(HeartbeatError):
            validate_response(
                self.mock_response(
                    url=OAUTH_BASE_URL + HEARTBEAT_ENDPOINT, status_code=403
                ),
                user_id=user_id,
            )

        # mock with a 403, and use url=oauth_base_url. assert raises invalid response error
        with self.assertRaises(InvalidResponseError):
            validate_response(
                self.mock_response(url=OAUTH_BASE_URL, status_code=403), user_id=user_id
            )

        # oauth_bas_url+timeseires and empty content, assert raises invalid response error
        with self.assertRaises(InvalidResponseError):
            validate_response(
                self.mock_response(
                    url=OAUTH_BASE_URL + TIMESERIES_ENDPOINT,
                    status_code=200,
                    content=b"",
                ),
                user_id=user_id,
            )

        # with 200 , and empty content, assert raises invalid response error
        with self.assertRaises(InvalidResponseError):
            validate_response(
                self.mock_response(url=OAUTH_TOKEN_URL, status_code=200, content=b""),
                user_id=user_id,
            )

        # with non-json content, assert raises invalid response error
        with self.assertRaises(InvalidResponseError):
            validate_response(
                self.mock_response(
                    url=OAUTH_TOKEN_URL, status_code=200, content=b"not json"
                ),
                user_id=user_id,
            )

    def test_request_wrapper(self):
        warnings.filterwarnings("ignore", category=UserWarning, module="logger")
        curr_logger_level: int = logging.getLogger().getEffectiveLevel()
        logging.getLogger().setLevel(logging.ERROR)
        user_id: str = f"User_{random_string()}"

        with self.assertRaises(ValueError):
            request_wrapper(method="pop", url=OAUTH_TOKEN_URL, user_id=user_id)

        def mock_auth_error(*args, **kwargs) -> requests.Response:
            return self.mock_response(url=OAUTH_TOKEN_URL, status_code=401)

        with mock.patch("requests.Session.send", side_effect=mock_auth_error):
            with self.assertRaises(AuthenticationError):
                request_wrapper(
                    method="get",
                    url=OAUTH_TOKEN_URL,
                    user_id=user_id,
                )

        def mock_heartbeat_error(*args, **kwargs) -> requests.Response:
            # mock a response with 403. assert raises heartbeat error
            return self.mock_response(
                url=OAUTH_BASE_URL + HEARTBEAT_ENDPOINT, status_code=403
            )

        with mock.patch("requests.Session.send", side_effect=mock_heartbeat_error):
            with self.assertRaises(HeartbeatError):
                request_wrapper(
                    method="get",
                    url=OAUTH_BASE_URL + HEARTBEAT_ENDPOINT,
                )

        def mock_known_errors(*args, **kwargs) -> requests.Response:
            # mock a response with 400. assert raises invalid response error
            raise ConnectionResetError

        with mock.patch("requests.Session.send", side_effect=mock_known_errors):
            with self.assertRaises(DownloadError):
                request_wrapper(
                    method="get",
                    url=OAUTH_BASE_URL + HEARTBEAT_ENDPOINT,
                )

        def mock_unknown_errors(*args, **kwargs) -> requests.Response:
            # raise some unrelated error -
            # using InvalidDataframeError as it does not interact with this scope
            raise InvalidDataframeError

        with mock.patch("requests.Session.send", side_effect=mock_unknown_errors):
            with self.assertRaises(InvalidDataframeError):
                request_wrapper(
                    method="get",
                    url=OAUTH_BASE_URL + HEARTBEAT_ENDPOINT,
                )

        def mock_keyboard_interrupt(*args, **kwargs) -> requests.Response:
            raise KeyboardInterrupt

        with mock.patch("requests.Session.send", side_effect=mock_keyboard_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                request_wrapper(
                    method="get",
                    url=OAUTH_BASE_URL + HEARTBEAT_ENDPOINT,
                )

        warnings.resetwarnings()
        logging.getLogger().setLevel(curr_logger_level)


class TestCertAuth(unittest.TestCase):
    def mock_isfile(self, path: str) -> bool:
        good_paths: List[str] = ["path/key.key", "path/crt.crt"]
        if path in good_paths:
            return True

    def good_args(self) -> Dict[str, str]:
        return {
            "username": "user",
            "password": "pass",
            "crt": "path/crt.crt",
            "key": "path/key.key",
        }

    def test_init(self):
        try:
            with mock.patch(
                "os.path.isfile", side_effect=lambda x: self.mock_isfile(x)
            ):
                certauth: CertAuth = CertAuth(**self.good_args())

                expctd_auth: str = base64.b64encode(
                    bytes(
                        f"{self.good_args()['username']}:{self.good_args()['password']}",
                        "utf-8",
                    )
                ).decode("ascii")
                self.assertEqual(certauth.auth, expctd_auth)
                self.assertEqual(certauth.crt, self.good_args()["crt"])
                self.assertEqual(certauth.key, self.good_args()["key"])

        except Exception as e:
            self.fail(f"Unexpected exception raised: {e}")

        with mock.patch("os.path.isfile", side_effect=lambda x: self.mock_isfile(x)):
            for key in self.good_args().keys():
                bad_args: Dict[str, str] = self.good_args().copy()
                bad_args[key] = 1
                with self.assertRaises(TypeError):
                    CertAuth(**bad_args)

        with mock.patch("os.path.isfile", side_effect=lambda x: self.mock_isfile(x)):
            for key in ["crt", "key"]:
                bad_args: Dict[str, str] = self.good_args().copy()
                bad_args[key] = "path/invalid_path"
                with self.assertRaises(FileNotFoundError):
                    CertAuth(**bad_args)

    def test_get_auth(self):
        with mock.patch("os.path.isfile", side_effect=lambda x: self.mock_isfile(x)):
            certauth: CertAuth = CertAuth(**self.good_args())

            expctd_auth: str = base64.b64encode(
                bytes(
                    f"{self.good_args()['username']}"
                    f":{self.good_args()['password']}",
                    "utf-8",
                )
            ).decode("ascii")
            self.assertEqual(certauth.auth, expctd_auth)
            self.assertEqual(certauth.crt, self.good_args()["crt"])
            self.assertEqual(certauth.key, self.good_args()["key"])

            authx: Dict[str, Dict[str, Any]] = certauth.get_auth()
            self.assertEqual(authx["headers"]["Authorization"], f"Basic {expctd_auth}")
            self.assertEqual(
                authx["cert"], (self.good_args()["crt"], self.good_args()["key"])
            )

    def test_with_dqinterface(self):
        with mock.patch("os.path.isfile", side_effect=lambda x: self.mock_isfile(x)):
            cfg: dict = dict(
                username="user", password="pass", crt="path/crt.crt", key="path/key.key"
            )
            dq_interface: DataQueryInterface = DataQueryInterface(**cfg, oauth=False)

            # assert that dq_interface.auth is CertAuth type
            self.assertIsInstance(dq_interface.auth, CertAuth)
            # check that the base_url is cert_base url
            self.assertEqual(dq_interface.base_url, CERT_BASE_URL)


##############################################


class TestOAuth(unittest.TestCase):
    def test_init(self):
        jpmaqs: JPMaQSDownload = JPMaQSDownload(
            oauth=True,
            client_id="test-id",
            client_secret="SECRET",
            check_connection=False,
        )
        self.assertEqual(jpmaqs.base_url, OAUTH_BASE_URL)

        with self.assertRaises(TypeError):
            OAuth(client_id="test-id", client_secret="SECRET", proxy="proxy")

    def test_invalid_init_args(self):
        good_args: Dict[str, str] = {
            "client_id": "test-id",
            "client_secret": "SECRET",
            "token_url": "https://token.url",
            "dq_resource_id": "test-resource-id",
        }

        for key in good_args.keys():
            bad_args: Dict[str, str] = good_args.copy()
            bad_args[key] = 1
            with self.assertRaises(TypeError):
                OAuth(**bad_args)

        try:
            oath_obj: OAuth = OAuth(**good_args)

            self.assertIsInstance(oath_obj.token_data, dict)
            expcted_token_data: Dict[str, str] = {
                "grant_type": "client_credentials",
                "client_id": "test-id",
                "client_secret": "SECRET",
                "aud": "test-resource-id",
            }
            self.assertEqual(oath_obj.token_data, expcted_token_data)
        except Exception as e:
            self.fail(f"Unexpected exception raised: {e}")

    def test_valid_token(self):
        oauth = OAuth(client_id="test-id", client_secret="SECRET")
        self.assertFalse(oauth._valid_token())


##############################################


class TestDataQueryInterface(unittest.TestCase):
    @staticmethod
    def jpmaqs_value(elem: str) -> float:
        """
        Use the mock jpmaqs_value to return a mock numerical jpmaqs value.
        """
        return mock_jpmaqs_value(elem=elem)

    def request_wrapper(
        self, dq_expressions: List[str], start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Use the mock request_wrapper to return a mock response.
        """
        return mock_request_wrapper(
            dq_expressions=dq_expressions, start_date=start_date, end_date=end_date
        )

    def test_init(self):
        def mock_isfile(path: str) -> bool:
            return path in ["path/key.key", "path/crt.crt"]

        with self.assertRaises(TypeError):
            DataQueryInterface(client_id=1, client_secret="SECRET")

        with self.assertRaises(ValueError):
            with self.assertWarns(UserWarning):
                dq_interface: DataQueryInterface = DataQueryInterface(
                    client_id=None,
                    client_secret=None,
                    oauth=True,
                )
        with mock.patch("os.path.isfile", side_effect=lambda x: mock_isfile(x)):
            with self.assertWarns(UserWarning):
                dq_interface: DataQueryInterface = DataQueryInterface(
                    client_id=None,
                    client_secret=None,
                    check_connection=False,
                    oauth=True,
                    username="user",
                    password="pass",
                    crt="path/crt.crt",
                    key="path/key.key",
                )

    @mock.patch(
        "macrosynergy.download.dataquery.OAuth._get_token",
        return_value=("SOME_TEST_TOKEN"),
    )
    @mock.patch(
        "macrosynergy.download.dataquery.request_wrapper",
        return_value=({"info": {"code": 200, "message": "Service Available."}}),
    )
    def test_check_connection(
        self, mock_p_request: mock.MagicMock, mock_p_get_token: mock.MagicMock
    ):
        # If the connection to DataQuery is working, the response code will invariably be
        # 200. Therefore, use the Interface Object's method to check DataQuery
        # connections.

        def _test(verbose: bool, raise_error: bool):
            with DataQueryInterface(
                client_id=random_string(), client_secret=random_string()
            ) as dq:
                self.assertTrue(
                    dq.check_connection(verbose=verbose, raise_error=raise_error)
                )

            mock_p_request.assert_called_once()
            mock_p_get_token.assert_called_once()
            return True

        for verbose in [True, False]:
            for raise_error in [True, False]:
                self.assertTrue(_test(verbose, raise_error))

    @mock.patch(
        "macrosynergy.download.dataquery.OAuth._get_token",
        return_value=("SOME_TEST_TOKEN"),
    )
    @mock.patch(
        "macrosynergy.download.dataquery.request_wrapper",
        return_value=({"info": {"code": 200, "message": "Service Available."}}),
    )
    def test_check_connection_on_init(
        self, mock_p_request: mock.MagicMock, mock_p_get_token: mock.MagicMock
    ):
        # If the connection to DataQuery is working, the response code will invariably be
        # 200. Therefore, use the Interface Object's method to check DataQuery
        # connections.

        with JPMaQSDownload(
            client_id="client1",
            client_secret="123",
            oauth=True,
        ) as jpmaqs:
            pass

        mock_p_request.assert_called_once()
        mock_p_get_token.assert_called_once()

    @mock.patch(
        "macrosynergy.download.dataquery.OAuth._get_token",
        return_value=random_string(),
    )
    @mock.patch(
        "macrosynergy.download.dataquery.request_wrapper",
        return_value=(
            {"info": {"code": 400}},
            False,
            {
                "headers": "{'Content-Type': 'application/json'}",
                "status_code": 400,
                "text": "{'error': 'invalid_request', 'error_description': 'The request is somehow corrupt.'}",
                "url": "https://api-developer.jpmorgan.com/research/dataquery-authe/api/v2/ **SOMETHING**",
            },
        ),
    )
    def test_check_connection_fail(self, mock_p_fail, mock_p_get_token):
        # Opposite of above method: if the connection to DataQuery fails, the error code
        # will be 400.
        curr_logger_level: int = logging.getLogger().getEffectiveLevel()
        logging.getLogger().setLevel(logging.ERROR)
        with JPMaQSDownload(
            client_id="client1", client_secret="123", oauth=True, check_connection=False
        ) as jpmaqs_download:
            # Method returns a Boolean. In this instance, the method should return False
            # (unable to connect).
            self.assertFalse(jpmaqs_download.check_connection())
        mock_p_fail.assert_called_once()
        mock_p_get_token.assert_called_once()
        logging.getLogger().setLevel(curr_logger_level)

    def test_oauth_condition(self):
        # Accessing DataQuery can be achieved via two methods: OAuth or Certificates /
        # Keys. To handle for the idiosyncrasies of the two access methods, split the
        # methods across individual Classes. The usage of each Class is controlled by the
        # parameter "oauth".
        # First check is that the DataQuery instance is using an OAuth Object if the
        # parameter "oauth" is set to to True.
        jpmaqs_download = JPMaQSDownload(
            oauth=True, client_id="client1", client_secret="123", check_connection=False
        )

        # check that jpmaqs_download is a superclass of dataquery interface
        self.assertIsInstance(jpmaqs_download, DataQueryInterface)

        self.assertIsInstance(jpmaqs_download.auth, OAuth)

    def test_certauth_condition(self):
        # Second check is that the DataQuery instance is using an CertAuth Object if the
        # parameter "oauth" is set to to False. The DataQuery Class's default is to use
        # certificate / keys.

        # Given the certificate and key will not point to valid directories, the expected
        # behaviour is for an OSError to be thrown.
        with self.assertRaises(FileNotFoundError):
            with JPMaQSDownload(
                username="user1",
                password="123",
                crt="/api_macrosynergy_com.crt",
                key="/api_macrosynergy_com.key",
                oauth=False,
                check_connection=False,
            ) as downloader:
                pass

 
    def test_dq_fetch(self):
        cfg: dict = dict(
            client_id=random_string(),
            client_secret=random_string(),
        )
        dq: DataQueryInterface = DataQueryInterface(oauth=True, **cfg)

        invl_responses: List[Any] = [
            None,
            {},
            {"attributes": []},
            {"attributes": [{"expression": "expression1"}]},
        ]

        dq.auth._stored_token = {
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "access_token": random_string(),
            "expires_in": 3600,
        }

        for invl_response in invl_responses:
            with mock.patch(
                "macrosynergy.download.dataquery.request_wrapper",
                return_value=invl_response,
            ):
                with self.assertRaises(InvalidResponseError):
                    dq._fetch(
                        url=OAUTH_BASE_URL + TIMESERIES_ENDPOINT,
                        params={"expr": "expression1"},
                    )

        invl_response: Dict[str, Any] = {
            "info": {"code": "204", "message": "No Content"}
        }
        with mock.patch(
            "macrosynergy.download.dataquery.request_wrapper",
            return_value=invl_response,
        ):
            with self.assertRaises(NoContentError):
                dq._fetch(
                    url=OAUTH_BASE_URL + CATALOGUE_ENDPOINT,
                    params={"group": "group-name"},
                )

    def test_download(self):
        good_args: Dict[str, Any] = {
            "expressions": ["expression1", "expression2"],
            "params": {"start_date": "2000-01-01", "end_date": "2020-01-01"},
            "url": OAUTH_BASE_URL + TIMESERIES_ENDPOINT,
            "tracking_id": str,
            "delay_param": 0.25,
            "retry_counter": 0,
        }

        bad_args: Dict[str, Any] = good_args.copy()
        bad_args["retry_counter"] = 10

        with mock.patch("sys.stdout", new=io.StringIO()) as mock_std:
            with mock.patch(
                "macrosynergy.download.dataquery.request_wrapper",
                return_value={"attributes": []},
            ):
                with self.assertRaises(DownloadError):
                    DataQueryInterface(
                        client_id="client_id",
                        client_secret="client_secret",
                        oauth=True,
                    )._download(**bad_args)
            err_string_1: str = (
                f"Retrying failed downloads. Retry count: {bad_args['retry_counter']}"
            )
            self.assertIn(err_string_1, mock_std.getvalue())

    def test_dq_download_args(self):
        good_args: Dict[str, Any] = {
            "expressions": ["DB(JPMAQS,EUR_FXXR_NSA,value)"],
            "start_date": "2020-01-01",
            "end_date": "2020-02-01",
            "show_progress": True,
            "endpoint": HEARTBEAT_ENDPOINT,
            "calender": "CAL_ALLDAYS",
            "frequency": "FREQ_DAY",
            "conversion": "CONV_LASTBUS_ABS",
            "nan_treatment": "NA_NOTHING",
            "reference_data": "NO_REFERENCE_DATA",
            "retry_counter": 0,
            "delay_param": API_DELAY_PARAM,
            "batch_size": 20,
        }
        self.assertTrue(validate_download_args(**good_args))

        # rplace expressions with None. should raise value error
        bad_args: Dict[str, Any] = good_args.copy()
        bad_args["expressions"] = None
        with self.assertRaises(ValueError):
            validate_download_args(**bad_args)

        # replace expressions with list of ints. should raise type error
        bad_args: Dict[str, Any] = good_args.copy()
        bad_args["expressions"] = [1, 2, 3]
        with self.assertRaises(TypeError):
            validate_download_args(**bad_args)

        # test all against an int (except retry_counter, batch_size)
        for key in good_args.keys():
            bad_value: Union[int, str] = 1
            if key in ["retry_counter", "batch_size"]:
                bad_value = "1"
            bad_args: Dict[str, Any] = good_args.copy()
            bad_args[key] = bad_value
            with self.assertRaises(TypeError):
                validate_download_args(**bad_args)

        # test delay_param
        for delay_param in [-0.1, -1.0]:
            bad_args: Dict[str, Any] = good_args.copy()
            bad_args["delay_param"] = delay_param
            with self.assertRaises(ValueError):
                validate_download_args(**bad_args)

        for delay_param in [0.0, 0.1, 0.15]:
            bad_args: Dict[str, Any] = good_args.copy()
            bad_args["delay_param"] = delay_param
            with self.assertWarns(RuntimeWarning):
                validate_download_args(**bad_args)

        for date_arg in ["start_date", "end_date"]:
            bad_args: Dict[str, Any] = good_args.copy()
            bad_args[date_arg] = "1-Jan-2023"
            with self.assertRaises(ValueError):
                validate_download_args(**bad_args)

        # if the batchsize if negative or non int, should raise type error
        for batch_size in [0.1, "1", None, [], {}]:
            bad_args: Dict[str, Any] = good_args.copy()
            bad_args["batch_size"] = batch_size
            with self.assertRaises(TypeError):
                validate_download_args(**bad_args)

        for batch_size in [-1, 0]:
            bad_args: Dict[str, Any] = good_args.copy()
            bad_args["batch_size"] = batch_size
            with self.assertRaises(ValueError):
                validate_download_args(**bad_args)

        # test that no warnings are raised if 1<bath_size<20
        for batch_size in [1, 19, 20]:
            good_args: Dict[str, Any] = good_args.copy()
            good_args["batch_size"] = batch_size
            # assert no warnings raised
            with warnings.catch_warnings(record=True) as w:
                validate_download_args(**good_args)
                self.assertEqual(len(w), 0)

        # test that >20 batch_size raises warning
        for batch_size in [21, 100]:
            bad_args: Dict[str, Any] = good_args.copy()
            bad_args["batch_size"] = batch_size
            with self.assertWarns(RuntimeWarning):
                validate_download_args(**bad_args)

    def test_get_unavailable_expressions(self):

        dq_interface = DataQueryInterface(
            client_id=random_string(),
            client_secret=random_string(),
            oauth=True,
            check_connection=False,
        )

        cids = ["AUD", "CAD", "CHF", "EUR"]
        xcats = ["EQXR_NSA", "FXXR_NSA"]
        metrics = ["value", "grading", "eop_lag", "mop_lag"]

        expression = construct_expressions(
            metrics=metrics,
            cids=cids,
            xcats=xcats,
        )

        # slect 10 random expressions
        unavailable_expressions = list(np.random.choice(expression, 10))
        expression = list(set(expression) - set(unavailable_expressions))

        dicts_list = self.request_wrapper(
            dq_expressions=expression,
            start_date="2000-01-01",
            end_date="2001-01-01",
        )

        mexprs = dq_interface._get_unavailable_expressions(
            expected_exprs=expression + unavailable_expressions,
            dicts_list=dicts_list,
        )
        self.assertEqual(set(mexprs), set(unavailable_expressions))


if __name__ == "__main__":
    unittest.main()
