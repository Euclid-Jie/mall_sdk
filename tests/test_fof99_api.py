import unittest
from unittest.mock import Mock, patch

import pandas as pd

from mall_sdk.FOF99Api import (
    FOF99Api,
    FOF99ApiError,
    FOF99CompanyNotFound,
    NavUploadPartialFailure,
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
    def make_nav_data(row_count, dates=None, codes=None, names=None):
        dates = dates if dates is not None else ["2026-08-26"] * row_count
        codes = codes if codes is not None else ["CODE1"] * row_count
        data = {
            "产品代码": codes,
            "日期": pd.to_datetime(dates),
            "单位净值": [1.0] * row_count,
            "累计净值": [1.0] * row_count,
        }
        if names is not None:
            data["产品名称"] = names
        return pd.DataFrame(data)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_returns_all_successful_chunk_results(self, post):
        first = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金1"]}}
        second = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金1"]}}
        post.side_effect = [make_response(first), make_response(second)]

        report = self.api.update_nav_to_FOF99(self.make_nav_data(1001))

        self.assertEqual(report.chunks, [first, second])
        self.assertEqual(len(report.uploaded), 1001)
        self.assertTrue(report.skipped.empty)
        self.assertEqual(post.call_count, 2)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_attributes_rejects_by_product_name_without_extra_requests(self, post):
        """平台回的是产品名：规范化后能在本地对上代码，就不该重传（保持 1 次请求）。"""
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {
                    "fail": ["睦沣一号:非交易日，无法上传净值"],
                    "success": ["基金2"],
                },
            }
        )
        nav_data = self.make_nav_data(
            2,
            ["2026-10-31", "2026-10-31"],
            ["SY7891", "SBUJ72"],
            ["睦沣一号私募证券投资基金", "凯双天山16号私募证券投资基金"],
        )

        report = self.api.update_nav_to_FOF99(nav_data)

        self.assertEqual(post.call_count, 1)  # 关键：没有多花请求
        self.assertEqual(report.uploaded["产品代码"].tolist(), ["SBUJ72"])
        self.assertEqual(report.skipped["产品代码"].tolist(), ["SY7891"])
        self.assertEqual(
            report.skipped["拒收原因"].tolist(), ["非交易日，无法上传净值"]
        )

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_attributes_glued_share_class_name(self, post):
        """实测例子：平台「凯丰凌风2号量化CTAB类」 vs 表内「…（B类份额）」，也要能对。"""
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {
                    "fail": ["凯丰凌风2号量化CTAB类:非交易日，无法上传净值"],
                    "success": ["基金2"],
                },
            }
        )
        nav_data = self.make_nav_data(
            2,
            ["2026-10-31"] * 2,
            ["BQG99B", "SBUJ72"],
            ["凯丰凌风2号量化CTA私募证券投资基金（B类份额）", "凯双天山16号私募证券投资基金"],
        )

        report = self.api.update_nav_to_FOF99(nav_data)

        self.assertEqual(post.call_count, 1)
        self.assertEqual(report.skipped["产品代码"].tolist(), ["BQG99B"])

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_raises_for_attributed_unexpected_reject_reason(self, post):
        """已归因但原因不在 skip_reasons（如代码不存在）→ 直接报错，且不重传。"""
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {
                    "fail": ["基金甲:代码不存在"],
                    "success": ["基金乙"],
                },
            }
        )
        nav_data = self.make_nav_data(
            2,
            ["2026-10-30", "2026-10-30"],
            ["CODE1", "CODE2"],
            ["基金甲私募证券投资基金", "基金乙私募证券投资基金"],
        )

        with self.assertRaisesRegex(RuntimeError, "代码不存在"):
            self.api.update_nav_to_FOF99(nav_data, isolate_failed=True)

        self.assertEqual(post.call_count, 1)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_attributed_batch_with_any_non_skip_reason_aborts(self, post):
        """同批里只要有一个已归因的非 skip 原因，就不能部分静默跳过、也不能重传。"""
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {
                    "fail": [
                        "睦沣一号:非交易日，无法上传净值",
                        "基金甲:代码不存在",
                    ],
                    "success": ["基金乙"],
                },
            }
        )
        nav_data = self.make_nav_data(
            3,
            ["2026-10-31"] * 3,
            ["SY7891", "CODE2", "SBUJ72"],
            [
                "睦沣一号私募证券投资基金",
                "基金甲私募证券投资基金",
                "基金乙私募证券投资基金",
            ],
        )

        with self.assertRaisesRegex(RuntimeError, "代码不存在"):
            self.api.update_nav_to_FOF99(nav_data, isolate_failed=True)

        self.assertEqual(post.call_count, 1)

    def test_normalize_name_keeps_share_class(self):
        self.assertEqual(
            FOF99Api._normalize_name("凯丰凌风2号量化CTAB类"),
            FOF99Api._normalize_name("凯丰凌风2号量化CTA私募证券投资基金（B类份额）"),
        )
        self.assertNotEqual(
            FOF99Api._normalize_name("微观博易-黎夏指增八号"),
            FOF99Api._normalize_name("微观博易-黎夏指增八号一期"),
        )

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_raises_when_reject_names_cannot_be_attributed(self, post):
        """没有产品名列（无法归因）且 isolate_failed=False → 直接报错，不多花请求。"""
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {"fail": ["睦沣一号:非交易日，无法上传净值"], "success": ["基金2"]},
            }
        )

        with self.assertRaisesRegex(RuntimeError, "非交易日"):
            self.api.update_nav_to_FOF99(self.make_nav_data(2))

        self.assertEqual(post.call_count, 1)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_empty_input_returns_empty_report_without_request(self, post):
        """没有待上传数据是正常状态，不该报错、也不该发请求。"""
        empty = pd.DataFrame(
            {
                "产品代码": pd.Series(dtype=str),
                "日期": pd.Series(dtype="datetime64[ns]"),
                "单位净值": pd.Series(dtype=float),
                "累计净值": pd.Series(dtype=float),
            }
        )

        report = self.api.update_nav_to_FOF99(empty)

        self.assertEqual(report.chunks, [])
        self.assertTrue(report.uploaded.empty)
        self.assertTrue(report.skipped.empty)
        post.assert_not_called()

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
    def test_skips_non_trading_day_products_reported_by_api(self, post):
        """整批被拒时逐产品重传，只把命中「非交易日」的产品计入 skipped。"""
        batch_fail = {
            "error_code": 0,
            "msg": "",
            "data": {
                "fail": ["睦沣一号:非交易日，无法上传净值"],
                "success": ["基金2"],
            },
        }
        code1_fail = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["睦沣一号:非交易日，无法上传净值"], "success": []},
        }
        code2_ok = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金2"]}}
        post.side_effect = [
            make_response(batch_fail),
            make_response(code1_fail),
            make_response(code2_ok),
        ]
        nav_data = pd.DataFrame(
            {
                "产品代码": ["CODE1", "CODE2"],
                "日期": pd.to_datetime(["2026-10-31", "2026-10-31"]),
                "单位净值": [1.0, 2.0],
                "累计净值": [1.0, 2.0],
            }
        )

        report = self.api.update_nav_to_FOF99(nav_data, isolate_failed=True)

        self.assertEqual(report.uploaded["产品代码"].tolist(), ["CODE2"])
        self.assertEqual(report.skipped["产品代码"].tolist(), ["CODE1"])
        self.assertEqual(
            report.skipped["拒收原因"].tolist(), ["非交易日，无法上传净值"]
        )
        self.assertEqual(post.call_count, 3)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_skips_single_product_reject_with_error_code(self, post):
        """实测形态：单产品拒收回 error_code=10001 + data=null，也要能归因并跳过。"""
        batch_fail = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["睦沣一号:非交易日，无法上传净值"], "success": ["基金2"]},
        }
        code1_fail = {
            "error_code": 10001,
            "msg": "睦沣一号:非交易日，无法上传净值",
            "data": None,
        }
        code2_ok = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金2"]}}
        post.side_effect = [
            make_response(batch_fail),
            make_response(code1_fail),
            make_response(code2_ok),
        ]
        nav_data = pd.DataFrame(
            {
                "产品代码": ["CODE1", "CODE2"],
                "日期": pd.to_datetime(["2026-10-31", "2026-10-31"]),
                "单位净值": [1.0, 2.0],
                "累计净值": [1.0, 2.0],
            }
        )

        report = self.api.update_nav_to_FOF99(nav_data, isolate_failed=True)

        self.assertEqual(report.uploaded["产品代码"].tolist(), ["CODE2"])
        self.assertEqual(report.skipped["产品代码"].tolist(), ["CODE1"])
        self.assertEqual(
            report.skipped["拒收原因"].tolist(), ["非交易日，无法上传净值"]
        )

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_batch_error_code_with_product_reason_goes_to_isolation(self, post):
        """整批回 error_code 非 0 但 msg 是「产品名:原因」→ 仍要进入逐产品定位。"""
        batch_reject = {
            "error_code": 10001,
            "msg": "睦沣一号:非交易日，无法上传净值",
            "data": None,
        }
        single_reject = {
            "error_code": 10001,
            "msg": "睦沣一号:非交易日，无法上传净值",
            "data": None,
        }
        post.side_effect = [make_response(batch_reject), make_response(single_reject)]

        report = self.api.update_nav_to_FOF99(self.make_nav_data(2), isolate_failed=True)

        self.assertTrue(report.uploaded.empty)
        self.assertEqual(len(report.skipped), 2)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_raises_for_unexpected_reject_reason(self, post):
        """原因不在 skip_reasons 里（如代码不存在）必须报错，不能静静吞掉。"""
        batch_fail = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["基金2:代码不存在"], "success": ["基金1"]},
        }
        code1_ok = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["基金1"]}}
        code2_fail = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["基金2:代码不存在"], "success": []},
        }
        post.side_effect = [
            make_response(batch_fail),
            make_response(code1_ok),
            make_response(code2_fail),
        ]
        nav_data = pd.DataFrame(
            {
                "产品代码": ["CODE1", "CODE2"],
                "日期": pd.to_datetime(["2026-10-30", "2026-10-30"]),
                "单位净值": [1.0, 2.0],
                "累计净值": [1.0, 2.0],
            }
        )

        with self.assertRaisesRegex(RuntimeError, "CODE2: 代码不存在"):
            self.api.update_nav_to_FOF99(nav_data, isolate_failed=True)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_extra_skip_reason_can_be_configured(self, post):
        """传 skip_reasons=("非交易日", "净值数据为空") 可一并剔掉空数据类拒收。"""
        batch_fail = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["量派聚核46号:净值数据为空"], "success": []},
        }
        single_fail = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["量派聚核46号:净值数据为空"], "success": []},
        }
        post.side_effect = [make_response(batch_fail), make_response(single_fail)]

        report = self.api.update_nav_to_FOF99(
            self.make_nav_data(
                1, ["2026-10-31"], ["SB4893"], ["量派聚核46号私募证券投资基金A"]
            ),
            skip_reasons=("非交易日", "净值数据为空"),
        )

        self.assertTrue(report.uploaded.empty)
        self.assertEqual(len(report.skipped), 1)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_isolate_failed_false_keeps_old_behaviour(self, post):
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {"fail": ["睦沣一号:非交易日，无法上传净值"], "success": ["基金2"]},
            }
        )

        with self.assertRaisesRegex(RuntimeError, "非交易日"):
            self.api.update_nav_to_FOF99(self.make_nav_data(2), isolate_failed=False)

        self.assertEqual(post.call_count, 1)

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


class UpdateNavProgressTest(unittest.TestCase):
    """回归：部分批次被拒时，已上传批次必须能立即回写，否则下次整批重传。"""

    def setUp(self):
        self.api = FOF99Api("appid", "appkey")
        self.marked: list[tuple[list[str], int]] = []

    def collect(self, report):
        self.marked.append(
            (report.uploaded["产品代码"].tolist(), len(report.skipped))
        )

    @staticmethod
    def nav(codes):
        return pd.DataFrame(
            {
                "产品代码": codes,
                "日期": pd.to_datetime(["2026-10-30"] * len(codes)),
                "单位净值": [1.0] * len(codes),
                "累计净值": [1.0] * len(codes),
                "产品名称": [f"{code}号私募证券投资基金" for code in codes],
            }
        )

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_on_chunk_fires_for_each_chunk_before_failure(self, post):
        """第 2 批有产品被非预期拒收，第 1 批的进度绝不能丢。"""
        ok = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["A"]}}
        reject = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["B号:净值日期不能早于基金成立日期"], "success": []},
        }
        post.side_effect = [make_response(ok), make_response(reject)]
        # 1001 行 → 两批：第 1 批 1000 行 CODE1，第 2 批 1 行 CODE2
        nav_data = pd.DataFrame(
            {
                "产品代码": ["CODE1"] * 1000 + ["CODE2"],
                "日期": pd.to_datetime(["2026-10-30"] * 1001),
                "单位净值": [1.0] * 1001,
                "累计净值": [1.0] * 1001,
                "产品名称": ["A号私募证券投资基金"] * 1000
                + ["B号私募证券投资基金"],
            }
        )

        with self.assertRaises(NavUploadPartialFailure) as ctx:
            self.api.update_nav_to_FOF99(nav_data, on_chunk=self.collect)

        # 第 1 批在上报错前就已经回调（这才是「不白烧额度」的关键）
        self.assertEqual(set(self.marked[0][0]), {"CODE1"})
        self.assertEqual(len(self.marked[0][0]), 1000)
        # 被拒的那批只把失败行留给调用方，不可标记
        self.assertEqual(ctx.exception.report.failed["产品代码"].tolist(), ["CODE2"])
        self.assertIn("净值日期不能早于基金成立日期", str(ctx.exception))
        self.assertEqual(post.call_count, 2)

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_unattributable_fail_name_falls_back_to_success_names(self, post):
        """fail 里的名字对不上表，但 success 能对上 → 仍零重传，且只标记平台确认的行。"""
        post.return_value = make_response(
            {
                "error_code": 0,
                "msg": "",
                "data": {
                    "fail": ["平台侧完全不同的名字:净值日期不能早于基金成立日期"],
                    "success": ["C号"],
                },
            }
        )
        nav_data = pd.DataFrame(
            {
                "产品代码": ["CODE1", "CODE2"],
                "日期": pd.to_datetime(["2026-10-30", "2026-10-30"]),
                "单位净值": [1.0, 1.0],
                "累计净值": [1.0, 1.0],
                "产品名称": ["D号私募证券投资基金", "C号私募证券投资基金"],
            }
        )

        with self.assertRaises(NavUploadPartialFailure) as ctx:
            self.api.update_nav_to_FOF99(nav_data, on_chunk=self.collect)

        self.assertEqual(post.call_count, 1)  # 关键：没有逐产品重传
        self.assertEqual(len(self.marked), 1)
        self.assertEqual(self.marked[0][0], ["CODE2"])  # 只有平台确认的 C号→CODE2
        self.assertEqual(ctx.exception.report.failed["产品代码"].tolist(), ["CODE1"])
        self.assertEqual(
            ctx.exception.report.failed["拒收原因"].tolist(),
            ["平台拒收（原因未能归因）"],
        )

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_partial_failure_still_uploads_remaining_chunks(self, post):
        """一个产品被拒不该让后面所有批都传不上去（否则每轮都卡在同一处）。"""
        first = {
            "error_code": 0,
            "msg": "",
            "data": {"fail": ["B号:净值日期不能早于基金成立日期"], "success": ["A号"]},
        }
        second = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["C号"]}}
        post.side_effect = [make_response(first), make_response(second)]
        # 第 1 批（1000 行）里有一个被拒；第 2 批（1 行）应该照传不误
        nav_data = pd.DataFrame(
            {
                "产品代码": ["CODEBAD"] + ["CODE2"] * 999 + ["CODE3"],
                "日期": pd.to_datetime(["2026-10-30"] * 1001),
                "单位净值": [1.0] * 1001,
                "累计净值": [1.0] * 1001,
                "产品名称": ["B号私募证券投资基金"]
                + ["A号私募证券投资基金"] * 999
                + ["C号私募证券投资基金"],
            }
        )

        with self.assertRaises(NavUploadPartialFailure) as ctx:
            self.api.update_nav_to_FOF99(nav_data, on_chunk=self.collect)

        self.assertEqual(post.call_count, 2)
        # 第 1 批里被平台收下的 999 行、第 2 批的 1 行，都已经回调
        self.assertEqual(len(self.marked), 2)
        self.assertEqual(set(self.marked[0][0]), {"CODE2"})
        self.assertEqual(len(self.marked[0][0]), 999)
        self.assertEqual(self.marked[1][0], ["CODE3"])
        self.assertEqual(ctx.exception.report.failed["产品代码"].tolist(), ["CODEBAD"])

    @patch("mall_sdk.FOF99Api.requests.post")
    def test_hard_error_keeps_previous_chunks_progress(self, post):
        """硬失败（签名/代码不存在）仍立即报错，但前面批次的进度已经回调过。"""
        ok = {"error_code": 0, "msg": "", "data": {"fail": [], "success": ["A"]}}
        hard = {"error_code": 1, "msg": "基金：BTE26B不存在;", "data": None}
        post.side_effect = [make_response(ok), make_response(hard)]

        with self.assertRaisesRegex(RuntimeError, "BTE26B不存在"):
            self.api.update_nav_to_FOF99(
                self.nav(["CODE1"] * 1000 + ["CODE2"]), on_chunk=self.collect
            )

        self.assertEqual(len(self.marked), 1)
        self.assertEqual(len(self.marked[0][0]), 1000)
        self.assertEqual(post.call_count, 2)


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
