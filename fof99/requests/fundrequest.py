# -*- coding: utf-8 -*-
# 私募基金相关请求
import time

from .baserequest import BaseRequest


class FundAdvancedList(BaseRequest):
    """ 根据平台/团队策略，获取基金列表数据 """
    _uri = '/fund/advancedlist'
    _filterer = lambda s, x: x['list']

    def set_params(self, strategy_one, strategy_two='不限', strategy_three='不限', type_=1,
                   page=1, pagesize=10, order_by='price_date', order=1):
        self['strategy_one'] = strategy_one
        self['strategy_two'] = strategy_two
        self['strategy_three'] = strategy_three
        self['type'] = type_
        self['page'] = page
        self['pagesize'] = pagesize
        self['order_by'] = order_by
        self['order'] = order


class FundInfo(BaseRequest):
    """ 提供私募基金基本信息数据 """
    _uri = '/fund/info'

    def set_params(self, reg_code):
        self['reg_code'] = reg_code


class FundPrice(BaseRequest):
    """ 提供私募基金平台净值的数据 """
    _uri = '/price'

    def set_params(self, reg_code, start_date=None, end_date=None, order_by='price_date', order=1):
        self['reg_code'] = reg_code
        if start_date:
            self['start_date'] = start_date
        if end_date:
            self['end_date'] = end_date

        self['order_by'] = order_by
        self['order'] = order


class FundCompanyPrice(BaseRequest):
    """ 提供私募基金团队净值的数据 """
    _uri = '/company/price'

    def set_params(self, reg_code, start_date=None, end_date=None, order_by='price_date', order=1):
        self['reg_code'] = reg_code
        if start_date:
            self['start_date'] = start_date
        if end_date:
            self['end_date'] = end_date
        self['order_by'] = order_by
        self['order'] = order


class FundMultiPrice(BaseRequest):
    """ 每次可查询多个基金的平台净值，最多不超过40只 """
    _uri = '/fund/price'

    def set_params(self, reg_code, date_=None, order_by='price_date', order=1):
        self['reg_code'] = reg_code
        if date_:
            self['date'] = date_
        self['order_by'] = order_by
        self['order'] = order


class FundMultiCompanyPrice(BaseRequest):
    """ 可查询多个基金的团队净值，最多不超过40只 """
    _uri = '/fund/company/price'

    def set_params(self, reg_code, date_=None, order_by='price_date', order=1):
        self['reg_code'] = reg_code
        if date_:
            self['date'] = date_
        self['order_by'] = order_by
        self['order'] = order


class PersonalFundPrice(BaseRequest):
    """ 根据自建基金id，查询净值。 """
    _uri = "/personal/funds/price"

    def set_params(self, fid, start_date=None, end_date=None, order_by='price_date', order=1):
        self['fid'] = fid
        if start_date:
            self['start_date'] = start_date
        if end_date:
            self['end_date'] = end_date
        self['order_by'] = order_by
        self['order'] = order


class MonitorLogList(BaseRequest):
    """ 查询分享给全团队的异常预警结果。 """
    _uri = "/monitor/log/list"

    def set_params(self, start_date=None, end_date=None, order_by='trigger_date', order=1):
        if start_date:
            self['start_date'] = start_date
        if end_date:
            self['end_date'] = end_date
        self['order_by'] = order_by
        self['order'] = order


class FofSubFundVirtualPrice(BaseRequest):
    """ 查询FOF基金下底层基金的虚拟净值。 """
    _uri = "/fof/subfund/virtual/price"

    def set_params(self, reg_code, start_date, end_date, source=1, cycle_type=1):
        self['reg_code'] = reg_code
        self['start_date'] = start_date
        self['end_date'] = end_date
        self['source'] = source
        self['cycleType'] = cycle_type


class DirectFundVirtualPrice(BaseRequest):
    """ 查询直投产品的虚拟净值。 """
    _uri = "/direct/fund/virtual/price"

    def set_params(self, reg_code, start_date, end_date, cust_name):
        self['reg_code'] = reg_code
        self['start_date'] = start_date
        self['end_date'] = end_date
        self['cust_name'] = cust_name


class FundScore(BaseRequest):
    """ 提供私募基金的模型评分信息 """
    _uri = "/fund/score"

    def set_params(self, reg_code, _date, model_source=1, price_source=1, fund_type=1):
        self['reg_code'] = reg_code
        self['date'] = _date
        self['model_source'] = model_source
        self['price_source'] = price_source
        self['fund_type'] = fund_type


class FofSubFund(BaseRequest):
    """ 基于FOF基金估值表，提供底层基金的持仓份额、金额、占比信息的查询。 """
    _uri = "/fof/sub/fund"

    def set_params(self, code, _date, _all=0):
        self['code'] = code
        self['date'] = _date
        self['all'] = _all


class FofSubFundDeals(BaseRequest):
    """ 查询FOF基金下，底层基金的交易记录。 """
    _uri = "/fof/subfund/deals"

    def set_params(self, code, page=1, page_size=10):
        self['code'] = code
        self['page'] = page
        self['pagesize'] = page_size


class CompanyPriceBatchAdd(BaseRequest):
    """ 支持已备案的私募基金上传团队净值。团队用户使用。 """
    _method = "POST"
    _uri = f"/company_price/batch/add"
    _sign_params = False
    _url_concat_sign = True

    def set_params(self, price_data):
        self['price_data'] = price_data


class PrivatePriceBatchAdd(BaseRequest):
    """ 支持已备案的私募基金上传私有净值。个人用户使用。 """
    _method = "POST"
    _uri = f"/private_price/batch/add"
    _sign_params = False
    _url_concat_sign = True

    def set_params(self, price_data):
        self['price_data'] = price_data


class InnerPriceBatchAdd(BaseRequest):
    """ 支持内部基金净值上传。 """
    _method = "POST"
    _uri = f"/inner_price/batch/add"
    _sign_params = False
    _url_concat_sign = True

    def set_params(self, price_data):
        self['price_data'] = price_data


class FofSubFundTrackList(BaseRequest):
    """ 查询团队各个基金列表的私募基金数据。"""
    _uri = "/fof/subfund/track/list"

    def set_params(self, type_, page=1, page_size=10):
        self['type'] = type_
        self['page'] = page
        self['pagesize'] = page_size
