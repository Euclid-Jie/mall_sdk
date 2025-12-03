# -*- coding: utf-8 -*-
# 因子相关请求

from .baserequest import BaseRequest


class FactorFutures(BaseRequest):
    """ 提供期货风格因子每日收益率数据 """
    _uri = '/factor/futures'

    def set_params(self, start_date=None, end_date=None, type_=3, sub_type='ALL', order=0):
        if start_date:
            self['start_date'] = start_date
        if end_date:
            self['end_date'] = start_date

        self['type'] = type_
        self['order'] = order
        self['sub_type'] = sub_type


class FactorStyleCne6(BaseRequest):
    """ 提供CNE6股票风格因子每日收益率数据 """
    _uri = '/factor/style/cne6'

    def set_params(self, start_date=None, end_date=None, order=0):
        if start_date:
            self['start_date'] = start_date
        if end_date:
            self['end_date'] = end_date
        self['order'] = order


class FactorStyleCne5(BaseRequest):
    """ 提供CNE5股票风格因子每日收益率数据 """
    _uri = '/factor/style/cne5'

    def set_params(self, start_date=None, end_date=None, order=0):
        if start_date:
            self['start_date'] = start_date
        if end_date:
            self['end_date'] = end_date
        self['order'] = order
