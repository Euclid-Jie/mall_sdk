import time
import requests
from typing import Literal
from hashlib import md5
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
import pandas as pd


class FOF99Api:
    def __init__(self, appid: str = "", appkey: str = "", token: str = ""):
        self.appid = appid
        self.appkey = appkey
        self.token = token

    def _update_nav_data_list_to_FOF99(
        self,
        update_nav_data_list: list[dict],
        type: Literal["inner", "company"] = "company",
    ):
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
        print(res.content.decode("utf-8"))

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
        assert set(nav_data_for_update.columns) > set(
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
        for i in range(0, nav_data_for_update.shape[0], 1000):
            sub_nav_data_df = nav_data_for_update.iloc[i : i + 1000, :]
            update_nav_data_list = self.generate_nav_data_list(sub_nav_data_df)
            self._update_nav_data_list_to_FOF99(update_nav_data_list, type)

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

    def get_company_info_from_code(self, comp_code) -> dict:
        url = f"https://api.huofuniu.com/newgoapi/company/advancedlist?token={self.token}&keyValue={comp_code}&member_type=%E4%B8%8D%E9%99%90&fund_num=-1&scale=0&found_date=0&active=1&company_manager_active=-1&page=1&pagesize=20&advise_type=0&order_by=fund_num&order=1&isReport=0"
        headers = {
            "access-token": self.token,
        }
        annlysis_data = requests.get(url=url, headers=headers)
        try:
            company_info = annlysis_data.json()["data"]["list"][0]
        except:
            raise ValueError("请检查token是否过期")
        return company_info

    def search_fund(self, keyword: str) -> list:
        url = f"https://api.huofuniu.com/newgoapi/fund/global/search?keyValue={keyword}"
        headers = {"access-token": self.token}
        res = requests.get(url=url, headers=headers)
        return res.json().get("data", [])

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
