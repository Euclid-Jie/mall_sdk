import unittest
from unittest.mock import Mock, patch

import pandas as pd

from mall_sdk.FOF99Api import (
    FOF99Api,
    FOF99ApiError,
    FOF99CompanyNotFound,
)


COMPANY_ROW = {
    "cancel_date": None,
    "company_name": "上海高毅资管",
    "fund_num": 359,
    "name_short": "上海高毅资管",
    "register_code": "P1002305",
    "scale": "100亿元以上",
}


def make_response(payload):
    response = Mock()
    response.text = str(payload)
    response.json.return_value = payload
    return response


class UpdateNavTest(unittest.TestCase):
    def setUp(self):
        self.api = FOF99Api("appid", "appkey")

    @staticmethod
    def make_nav_data(row_count):
        return pd.DataFrame(
            {
                "产品代码": ["CODE1"] * row_count,
                "日期": pd.to_datetime(["2026-08-26"] * row_count),
                "单位净值": [1.0] * row_count,
                "累计净值": [1.0] * row_count,
            }
        )

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_returns_all_successful_chunk_results(self, post):
        first = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金1"]}}
        second = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金1"]}}
        post.side_effect = [make_response(first), make_response(second)]

        results = self.api.update_nav_to_FOF99(self.make_nav_data(1001))

        self.assertEqual(results, [first, second])
        self.assertEqual(post.call_count, 2)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_raises_as_soon_as_any_chunk_fails(self, post):
        success = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金1"]}}
        failure = {"error_code": 1, "msg": "基金：BTE26B不存在;", "data": None}
        unused = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金1"]}}
        post.side_effect = [
            make_response(success),
            make_response(failure),
            make_response(unused),
        ]

        with self.assertRaisesRegex(RuntimeError, "BTE26B不存在"):
            self.api.update_nav_to_FOF99(self.make_nav_data(2001))

        self.assertEqual(post.call_count, 2)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_raises_when_response_contains_failed_funds(self, post):
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {"fail": ["基金2"], "success": ["基金1"]},
            }
        )

        with self.assertRaisesRegex(RuntimeError, "基金2"):
            self.api._update_nav_data_list_to_FOF99(
                [{"code": "CODE1", "nets": []}, {"code": "CODE2", "nets": []}]
            )


class CompanyInfoTest(unittest.TestCase):
    def setUp(self):
        self.api = FOF99Api("appid", "appkey", token="web-token")

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_returns_company_row_with_browser_user_agent(self, get):
        get.return_value = make_response(
            {"error_code": 0, "msg": "", "data": {"list": [COMPANY_ROW], "total": 1}}
        )

        self.assertEqual(self.api.get_company_info_from_code("P1002305"), COMPANY_ROW)

        request = get.call_args
        self.assertEqual(request.kwargs["params"]["active"], "1")
        self.assertEqual(request.kwargs["params"]["keyValue"], "P1002305")
        # 缺少浏览器 UA 时接口会返回 error_code=0 + data=null，因此必须显式覆盖
        self.assertNotIn("python-requests", request.kwargs["headers"]["User-Agent"])
        self.assertTrue(request.kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0"))
        self.assertEqual(request.kwargs["timeout"], 30)

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_null_data_is_reported_as_request_failure_not_token_only(self, get):
        get.return_value = make_response({"error_code": 0, "msg": "", "data": None})

        with self.assertRaisesRegex(FOF99ApiError, "data=null"):
            self.api.get_company_info_from_code("P1002305")

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_auth_error_reports_error_code(self, get):
        get.return_value = make_response(
            {"error_code": -4, "msg": "token check fail", "data": None}
        )

        with self.assertRaisesRegex(FOF99ApiError, "error_code=-4"):
            self.api.get_company_info_from_code("P1002305")

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_falls_back_to_cancelled_managers(self, get):
        cancelled = dict(COMPANY_ROW, register_code="P1010118", cancel_date="2025-12-12")
        get.side_effect = [
            make_response({"error_code": 0, "msg": "", "data": {"list": [], "total": 0}}),
            make_response(
                {"error_code": 0, "msg": "", "data": {"list": [cancelled], "total": 1}}
            ),
        ]

        info = self.api.get_company_info_from_code("P1010118")

        self.assertEqual(info["cancel_date"], "2025-12-12")
        self.assertEqual(
            [call.kwargs["params"]["active"] for call in get.call_args_list],
            ["1", "-1"],
        )

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_raises_not_found_when_both_queries_are_empty(self, get):
        get.return_value = make_response(
            {"error_code": 0, "msg": "", "data": {"list": [], "total": 0}}
        )

        with self.assertRaises(FOF99CompanyNotFound):
            self.api.get_company_info_from_code("ZZZZZZZZ")

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_prefers_exact_register_code_match(self, get):
        other = dict(COMPANY_ROW, register_code="P1002306", name_short="上海高毅资管二号")
        get.return_value = make_response(
            {"error_code": 0, "msg": "", "data": {"list": [other, COMPANY_ROW]}}
        )

        info = self.api.get_company_info_from_code("P1002305")

        self.assertEqual(info["register_code"], "P1002305")

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_unmatched_company_rows_are_not_returned_as_target(self, get):
        other = dict(COMPANY_ROW, register_code="P1002306", name_short="其他管理人")
        get.return_value = make_response(
            {"error_code": 0, "msg": "", "data": {"list": [other], "total": 1}}
        )

        with self.assertRaises(FOF99CompanyNotFound):
            self.api.get_company_info_from_code("P1002305")

        self.assertEqual(
            [call.kwargs["params"]["active"] for call in get.call_args_list],
            ["1", "-1"],
        )

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_search_fund_includes_token_query_parameter(self, get):
        get.return_value = make_response({"error_code": 0, "msg": "", "data": []})

        self.assertEqual(self.api.search_fund("高毅"), [])

        self.assertEqual(
            get.call_args.kwargs["params"],
            {"token": "web-token", "keyValue": "高毅"},
        )

    @patch("mall_sdk.FOF99Api.requests.get")
    def test_search_fund_rejects_null_data(self, get):
        get.return_value = make_response({"error_code": 0, "msg": "", "data": None})

        with self.assertRaisesRegex(FOF99ApiError, "data=null"):
            self.api.search_fund("高毅")


if __name__ == "__main__":
    unittest.main()
