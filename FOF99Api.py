import time
import requests
from typing import Literal
from hashlib import md5
import pandas as pd

try:
    from .fof99 import (
        PersonalFundPrice,
        FundInfo,
        FundPrice,
        FundCompanyPrice,
        GmFundPrice,
        FundMultiCompanyPrice,
        FundMultiPrice,
        CompanyInfo,
    )
    from .scraper import get_fof99_web_token
except ImportError:
    from fof99 import (
        PersonalFundPrice,
        FundInfo,
        FundPrice,
        FundCompanyPrice,
        GmFundPrice,
        FundMultiCompanyPrice,
        FundMultiPrice,
        CompanyInfo,
    )
    from scraper import get_fof99_web_token


class FOF99ApiError(RuntimeError):
    """FOF99 网页接口请求失败或返回体不符合预期。"""


class FOF99CompanyNotFound(FOF99ApiError):
    """FOF99 未收录目标管理人（含已注销管理人）。"""


class FOF99Api:
    WEB_API_BASE = "https://api.huofuniu.com"
    WEB_BASE_URL = "https://mp.fof99.com"
    WEB_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    )

    def __init__(
        self,
        appid: str = "",
        appkey: str = "",
        token: str = "",
        timeout: int = 30,
    ):
        self.appid = appid
        self.appkey = appkey
        self.token = token
        self.timeout = timeout

    def _get_web_token(self) -> str:
        token = self.token or get_fof99_web_token()
        if not token:
            raise ValueError("请在 FOF99Api(token=...) 或 .env 中配置 FOF99_WEB_TOKEN")
        return token

    def _web_headers(self, referer: str = "/") -> dict:
        """构造 api.huofuniu.com 网页接口的请求头。

        注意：这些接口除 token 外还按 User-Agent 过滤请求。使用 requests 默认
        UA（``python-requests/x.y``）、空 UA 或缺少 UA 时，接口仍返回
        HTTP 200 且 ``error_code=0``，但 ``data`` 为 ``null``，看起来像「没有数据」。
        所以只带 ``access-token`` 是不够的，必须显式带浏览器 UA。
        鉴权本身只依赖查询参数 ``token``；``access-token`` 头仅为兼容保留。
        """
        if not referer.startswith("http"):
            referer = f"{self.WEB_BASE_URL}{referer}"
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": self.WEB_BASE_URL,
            "Referer": referer,
            "User-Agent": self.WEB_USER_AGENT,
            "access-token": self._get_web_token(),
        }

    @staticmethod
    def _parse_web_payload(res: requests.Response, action: str) -> dict:
        """统一校验网页接口返回体，避免把失败当成「查不到数据」。"""
        res.raise_for_status()
        try:
            payload = res.json()
        except ValueError as exc:
            raise FOF99ApiError(
                f"{action}失败: API 响应不是有效的 JSON（{res.text[:200]!r}）"
            ) from exc
        if not isinstance(payload, dict):
            raise FOF99ApiError(f"{action}失败: API 响应必须是 JSON 对象")
        error_code = payload.get("error_code")
        if error_code != 0:
            raise FOF99ApiError(
                f"{action}失败: error_code={error_code}, msg={payload.get('msg')!r}"
                "；error_code=-4 表示 token 缺失或失效，请更新 FOF99_WEB_TOKEN"
            )
        return payload
    @staticmethod
    def _parse_fund_view_id(fid_or_url: str) -> str:
        fid_or_url = str(fid_or_url).strip()
        if "/fund/view/" in fid_or_url:
            return (
                fid_or_url.split("/fund/view/", 1)[1].split("?", 1)[0].split("#", 1)[0]
            )
        return fid_or_url

    def get_fund_basic_info_from_id(self, fid_or_url: str) -> dict:
        """
        通过 FOF99 网页基金 ID 获取基金基本信息。

        参数可以传基金 ID，也可以传完整详情页 URL，例如：
        https://mp.fof99.com/fund/view/1efcf35e914e1b54

        Returns:
            dict: 包含产品名称、备案编号、公司管理规模等字段。
        """
        fid = self._parse_fund_view_id(fid_or_url)
        url = f"{self.WEB_API_BASE}/newgoapi/funds/analyze"
        res = requests.get(
            url,
            params={
                "token": self._get_web_token(),
                "id": fid,
                "url": "",
            },
            headers=self._web_headers(f"/fund/view/{fid}"),
            timeout=self.timeout,
        )
        payload = self._parse_web_payload(res, "获取基金基本信息")
        data = payload.get("data") or {}
        if not data:
            raise FOF99ApiError(
                f"获取基金基本信息失败: 接口未返回数据（fid={fid}），"
                "请检查 token 是否有效或 User-Agent 是否被拦截"
            )
        return {
            "产品名称": data.get("fund_short_name") or data.get("fund_name"),
            "产品全称": data.get("fund_name"),
            "备案编号": data.get("register_number"),
            "公司管理规模": data.get("scale"),
            "管理人": data.get("advisor"),
            "fid": data.get("id") or fid,
            "company_id": data.get("company_id"),
        }

    def _update_nav_data_list_to_FOF99(
        self,
        update_nav_data_list: list[dict],
        type: Literal["inner", "company"] = "company",
    ) -> dict:
        # 上传净值数据到火富牛FOF99
        sign = md5(
            f"app_id={self.appid}&tm={int(time.time())}{self.appkey}".encode()
        ).hexdigest()
        url = f"https://mallapi.huofuniu.com/{type}_price/batch/add?app_id={self.appid}&sign={sign}&tm={int(time.time())}"
        res = requests.post(
            url,
            json={
                "price_data": update_nav_data_list,
            },
        )
        print(res.text)
        res.raise_for_status()
        try:
            payload = res.json()
        except ValueError as exc:
            raise RuntimeError("FOF99净值上传失败: API 响应不是有效的 JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("FOF99净值上传失败: API 响应必须是 JSON 对象")

        data = payload.get("data")
        success = data.get("success") if isinstance(data, dict) else None
        fail = data.get("fail") if isinstance(data, dict) else None
        expected_count = len(update_nav_data_list)
        success_count = len(success) if isinstance(success, list) else 0
        if (
            payload.get("error_code") != 0
            or not isinstance(data, dict)
            or bool(fail)
            or not isinstance(success, list)
            or success_count != expected_count
        ):
            raise RuntimeError(
                "FOF99净值上传失败: "
                f"error_code={payload.get('error_code')}, msg={payload.get('msg')!r}, "
                f"fail={fail!r}, success_count={success_count}, "
                f"expected_count={expected_count}"
            )
        return payload

    @staticmethod
    def generate_nav_data_list(sub_nav_data_df: pd.DataFrame) -> list[dict]:
        # 挨个产品添加
        product_code_list = sub_nav_data_df["产品代码"].unique()
        update_nav_data_list = []
        for code in product_code_list:
            single_nav_data = sub_nav_data_df[sub_nav_data_df["产品代码"] == code]
            result = [
                {
                    "date": row["日期"],
                    "price": str(row["单位净值"]),
                    "cumulative_nav_withdrawal": str(row["累计净值"]),
                }
                for _, row in single_nav_data.iterrows()
            ]
            update_nav_data_list.append(
                {
                    "code": code,
                    "nets": result,
                }
            )
        return update_nav_data_list

    def update_nav_to_FOF99(
        self,
        nav_data_for_update: pd.DataFrame,
        type: Literal["inner", "company"] = "company",
    ) -> list[dict]:
        """
        转换数据格式并上传到FOF99
        Parameters
        """
        # 防止修改原数据
        nav_data_for_update = nav_data_for_update.copy()
        assert nav_data_for_update.shape[0] > 0, "没有需要更新的数据！"
        # 确认字段
        expected_columns = ["产品代码", "日期", "单位净值", "累计净值"]
        assert set(nav_data_for_update.columns) >= set(
            expected_columns
        ), "字段不匹配，请检查！期望字段: {}，实际字段: {}".format(
            expected_columns, nav_data_for_update.columns.tolist()
        )
        # 日期格式转换
        assert (
            nav_data_for_update["日期"].dtype == "datetime64[ns]"
        ), "日期格式错误，请检查！"
        nav_data_for_update["日期"] = nav_data_for_update["日期"].dt.strftime(
            "%Y-%m-%d"
        )
        # 分多个chuck上传
        results = []
        for i in range(0, nav_data_for_update.shape[0], 1000):
            sub_nav_data_df = nav_data_for_update.iloc[i : i + 1000, :]
            update_nav_data_list = self.generate_nav_data_list(sub_nav_data_df)
            results.append(
                self._update_nav_data_list_to_FOF99(update_nav_data_list, type)
            )
        return results

    def get_fund_info(self, reg_code: str = "SVZ009"):
        req = FundInfo(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code)
        res = req.do_request(use_df=False)
        return res

    def get_fund_price(
        self,
        reg_code: str = "SVZ009",
        start_date: str = "2010-01-01",
    ):
        req = FundPrice(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code=reg_code, start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_person_fund_price(
        self,
        fid: str = "381719",
        start_date: str = "2010-01-01",
    ):
        req = PersonalFundPrice(self.appid, self.appkey)  # 请求对
        req.set_params(fid=fid, start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_company_price(
        self,
        reg_code: str = "JX919A",
        start_date: str = "2010-01-01",
    ):
        req = FundCompanyPrice(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code=reg_code, start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_public_fund_price(
        self,
        reg_code="022461",
        start_date: str = "2010-01-01",
    ) -> pd.DataFrame:
        req = GmFundPrice(self.appid, self.appkey)  # 请求对
        req.set_params(str(reg_code).zfill(6), start_date=start_date)
        res = req.do_request(use_df=True)
        return res

    def get_multi_price(
        self,
        reg_codes: list,
        date: str = None,
    ):
        def chunk_list(lst, chunk_size):
            """Helper function to split a list into chunks."""
            for i in range(0, len(lst), chunk_size):
                yield lst[i : i + chunk_size]

        all_results = []
        for chunk in chunk_list(reg_codes, chunk_size=40):
            req = FundMultiPrice(self.appid, self.appkey)  # 请求对
            req.set_params(
                order="0", order_by="nav", reg_code=",".join(chunk), date_=date
            )
            res = req.do_request(use_df=True)
            all_results.append(res)
        return pd.concat(all_results, ignore_index=True)

    def get_multi_company_price(
        self,
        reg_codes: list,
        date: str = None,
    ):
        def chunk_list(lst, chunk_size):
            """Helper function to split a list into chunks."""
            for i in range(0, len(lst), chunk_size):
                yield lst[i : i + chunk_size]

        all_results = []
        for chunk in chunk_list(reg_codes, chunk_size=40):
            req = FundMultiCompanyPrice(self.appid, self.appkey)  # 请求对
            req.set_params(
                order="0", order_by="nav", reg_code=",".join(chunk), date_=date
            )
            res = req.do_request(use_df=True)
            all_results.append(res)
        return pd.concat(all_results, ignore_index=True)

    def get_company_info_from_code(
        self, comp_code, include_cancelled: bool = True
    ) -> dict:
        """按管理人登记编号（或名称）获取 FOF99 管理人信息。

        FOF99 的 ``company/advancedlist`` 默认只返回正常运作的管理人；已注销的
        管理人（``cancel_date`` 非空）必须用 ``active=-1`` 才能查到。因此这里先查
        正常运作，查不到再回退到 ``active=-1``，避免把已注销管理人或未收录管理人
        误判成 token 失效。

        Raises:
            FOF99CompanyNotFound: FOF99 确实没有收录该管理人。
            FOF99ApiError: 鉴权、网络或返回体异常。
        """
        key_value = str(comp_code).strip()
        if not key_value:
            raise ValueError("comp_code 不能为空")

        company = self._find_company(key_value, active="1")
        if company is None and include_cancelled:
            company = self._find_company(key_value, active="-1")
        if company is None:
            raise FOF99CompanyNotFound(
                f"FOF99 未收录管理人 {key_value}（active=1 与 active=-1 均无结果）"
            )
        return company

    def _find_company(self, key_value: str, active: str) -> dict | None:
        res = requests.get(
            f"{self.WEB_API_BASE}/newgoapi/company/advancedlist",
            params={
                "token": self._get_web_token(),
                "keyValue": key_value,
                "member_type": "不限",
                "fund_num": "-1",
                "scale": "0",
                "found_date": "0",
                "active": active,
                "company_manager_active": "-1",
                "page": "1",
                "pagesize": "20",
                "advise_type": "0",
                "order_by": "fund_num",
                "order": "1",
                "isReport": "0",
            },
            headers=self._web_headers(f"/company/index?keyValue={key_value}"),
            timeout=self.timeout,
        )
        payload = self._parse_web_payload(res, f"查询管理人 {key_value}")
        data = payload.get("data")
        if data is None:
            raise FOF99ApiError(
                f"查询管理人 {key_value} 失败: 接口返回 error_code=0 但 data=null"
                "，通常是 token 失效或 User-Agent 被拦截，而不是没有数据"
            )
        if not isinstance(data, dict):
            raise FOF99ApiError(f"查询管理人 {key_value} 失败: data 格式异常 {data!r}")
        rows = data.get("list") or []
        if not isinstance(rows, list):
            raise FOF99ApiError(
                f"查询管理人 {key_value} 失败: list 格式异常 {rows!r}"
            )
        return self._match_company(rows, key_value)

    @staticmethod
    def _match_company(rows: list[dict], key_value: str) -> dict | None:
        """在返回列表中定位目标管理人；没有精确匹配时返回 None。"""
        if not rows:
            return None
        target = str(key_value).strip()
        target_upper = target.upper()
        for row in rows:
            if str(row.get("register_code") or "").strip().upper() == target_upper:
                return row
        for row in rows:
            names = {
                str(row.get(field) or "").strip()
                for field in ("name_short", "company_name", "name_cn")
            }
            if target in names:
                return row
        return None

    def search_fund(self, keyword: str) -> list:
        res = requests.get(
            f"{self.WEB_API_BASE}/newgoapi/fund/global/search",
            params={"token": self._get_web_token(), "keyValue": keyword},
            headers=self._web_headers("/fund/index"),
            timeout=self.timeout,
        )
        payload = self._parse_web_payload(res, f"搜索基金 {keyword}")
        data = payload.get("data")
        if data is None:
            raise FOF99ApiError(
                f"搜索基金 {keyword} 失败: 接口返回 error_code=0 但 data=null"
                "，通常是 token 失效或 User-Agent 被拦截，而不是没有数据"
            )
        if not isinstance(data, list):
            raise FOF99ApiError(f"搜索基金 {keyword} 失败: data 格式异常 {data!r}")
        return data

    def get_fund_info_from_code(self, registerNo) -> pd.DataFrame:
        """
        通过管理人登记编号获取基金信息

        Returns:
            pd.DataFrame: 包含以下字段的基金信息数据框
            - legal_person_name: 上海高毅投资管理有限公司
            - credit_no: 91310120069360143D
            - business_term: 2013-05-29至2033-05-28
            - business_scope: 资产管理，投资管理。\r\n【依法须经批准的项目，经相关部门批准后方可开展经营活动】
            - register_address: 上海市奉贤区青村镇奉村路458号1幢221室
            - register_code: P1002305
            - name_cn: 上海高毅资产管理合伙企业（有限合伙）
            - name_short: 上海高毅资管
            - strategy: 股票多头
            - scale: 100亿元以上
            - found_date: 2013-05-29
            - fund_num: 370
            - member_type: 普通会员
            - register_capital: 35833
            - paid_capital: 35833
            - main_type: 私募证券投资基金管理人
            - office_address: 广东省深圳市福田区中心四路一号深圳嘉里建设广场3座25层
        """
        #
        req = CompanyInfo(self.appid, self.appkey)  # 请求对
        req.set_params(reg_code=registerNo)
        res = req.do_request(use_df=True)
        return res
