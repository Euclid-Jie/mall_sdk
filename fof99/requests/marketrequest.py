# -*- coding: utf-8 -*-
# 市场相关请求

from .baserequest import BaseRequest


class MarketDiscountRate(BaseRequest):
    """ 市场-股指期货升贴水率查询 """
    _uri = "/market/discountRate"

    def set_params(self, start_date, end_date, _type):
        self['start_date'] = start_date
        self['end_date'] = end_date
        self['type'] = _type


class MarketFutureBasis(BaseRequest):
    """市场-市场-基差走势查询。股指基差=期货合约收盘价-现货指数收盘价"""
    _uri = "/market/future/basis"

    def set_params(self, start_date, end_date):
        self['start_date'] = start_date
        self['end_date'] = end_date


class MarketCategory(BaseRequest):
    """市场-策略观察中指标分布查询。"""
    _uri = "/market/category"

    def set_params(self, ids, _type, end_date):
        self['ids'] = ids
        self['type'] = _type
        self['end_date'] = end_date


class MarketWeekReport(BaseRequest):
    """研选-火富牛私募产品跟踪周报查询。"""
    _uri = "/market/week/report"
