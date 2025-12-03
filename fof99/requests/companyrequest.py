# -*- coding: utf-8 -*-
# 投资顾问相关
import time

from .baserequest import BaseRequest


class CompanyInfo(BaseRequest):
    """ 提供投资顾问的信息 """
    _uri = '/company/info'

    def set_params(self, reg_code):
        self['code'] = reg_code


class CompanyScale(BaseRequest):
    """ 提供投资顾问的信息 """
    _uri = '/company/scale'

    def set_params(self, code):
        self['code'] = code


class CompanyShareholder(BaseRequest):
    """ 私募管理人股东信息查询 """
    _uri = '/company/shareholder'

    def set_params(self, code):
        self['code'] = code


class CompanyFundList(BaseRequest):
    """ 提供私募管理人的旗下基金列表。 """
    _uri = '/company/fund/list'

    def set_params(self, code, product_type=None, page=1, page_size=20):
        self['code'] = code
        if product_type is not None:
            self['product_type'] = product_type
        self['page'] = page
        self['pagesize'] = page_size
