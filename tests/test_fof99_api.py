import unittest
from unittest.mock import Mock, patch

import pandas as pd

from mall_sdk.FOF99Api import FOF99Api


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


if __name__ == "__main__":
    unittest.main()
