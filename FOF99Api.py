import requests
from fof99 import (
    PersonalFundPrice,
    FundInfo,
    FundPrice,
    FundCompanyPrice,
    GmFundPrice,
    FundMultiCompanyPrice,
    FundMultiPrice,
)
import numpy as np
import pandas as pd


class FOF99Api:
    appid: str = ""
    appkey: str = ""
    token: str = ""

    def __init__(self):
        pass

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

    def get_fund_info_from_code(self, reg_code) -> str:
        # TODO: 通过基金代码获取基金信息
        pass
