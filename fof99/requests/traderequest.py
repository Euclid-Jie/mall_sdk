# -*- coding: utf-8 -*-
# 交易相关

from .baserequest import BaseRequest


class FundBuyInfo(BaseRequest):
    """ 提供【投资-直投产品】列表中公/私募基金的交易记录数据 """
    _uri = '/fund/buy/info'

    def set_params(self, pid, start_date=None, end_date=None):
        self['pid'] = pid
        if start_date:
            self['start_time'] = start_date
        if end_date:
            self['end_time'] = end_date


class FofInvestCustomerPrice(BaseRequest):
    """ 查询直投产品拟合的组合的净值。 """
    _uri = '/fof/invest/customer/price'

    def set_params(self, start_date=None, end_date=None, pid=""):
        if start_date is not None:
            self['start_date'] = start_date
        if end_date is not None:
            self['end_date'] = end_date
        if pid != "":
            self['pid'] = pid


class FofInvestFundScale(BaseRequest):
    """ 直投组合持仓规模查询。 """
    _uri = '/fof/invest/fund/scale'

    def set_params(self, end_date=None, pid=""):
        if end_date is not None:
            self['end_date'] = end_date

        if pid != "":
            self['pid'] = pid
