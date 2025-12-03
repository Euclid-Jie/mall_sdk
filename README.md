# 火富牛SDK

## SDK请求类

```
    FactorFutures：提供期货风格因子每日收益率数据
    FactorStyleCne6：提供CNE6股票风格因子每日收益率数据
    FactorStyleCne5：提供CNE5股票风格因子每日收益率数据
    
    IndexPrice：提供基准指数的行情数据查询
    IndexBatchPrice：多指数行情查询
    IndexStockAmt：提供股票指数的成交额数据
    IndexStockTurn：提供股票指数的换手率数据
    IndexStockPE：提供股票指数的PE（TTM）中位数数据
    
    FundAdvancedList：根据平台/团队策略，获取基金列表数据
    FundInfo：提供私募基金基本信息数据
    FundPrice：提供私募基金平台净值的数据
    FundCompanyPrice：提供私募基金团队净值的数据
    FundMultiPrice：每次可查询多个基金的平台净值，最多不超过40只
    PersonalFundPrice：根据自建基金id，查询净值
    MonitorLogList：查询分享给全团队的异常预警结果
    FofSubFundVirtualPrice：查询FOF基金下底层基金的虚拟净值
    DirectFundVirtualPrice：查询直投产品的虚拟净值
    FundScore：提供私募基金的模型评分信息
    FofSubFund：基于FOF基金估值表，提供底层基金的持仓份额、金额、占比信息的查询
    FofSubFundDeals：查询FOF基金下，底层基金的交易记录
    CompanyPriceBatchAdd：已备案的私募基金上传团队净值。团队用户使用
    PrivatePriceBatchAdd：已备案的私募基金上传私有净值。个人用户使用
    InnerPriceBatchAdd：内部基金净值上传
    FofSubFundTrackList：查询团队各个基金列表的私募基金数据
    
    IndexPrice：提供基准指数的行情数据查询
    IndexBatchPrice：查询多个指数的行情数据，最多不超过40只
    IndexStockAmt：提供股票指数的成交额数据
    IndexStockTurn：提供股票指数的换手率数据
    IndexStockPE：提供股票指数的PE（TTM）中位数数据 
    PrivateIndexPrice：根据自建指数id，查询指数行情

    GmFundInfo：提供公募基金基本信息数据
    GmFundPrice：提供公募基金净值的数据
    GmFundBatchPrice：公募基金多基金净值
    
    FoCombiPrice：提供团队/我的实盘组合净值的数据
    CombiPrice：提供团队/我的模拟组合净值的数据
    
    CompanyInfo：提供投资顾问的信息
    CompanyScale：提供私募管理人的协会管理规模、披露规模、运作产品数的信息
    CompanyShareholder：提供私募管理人的股东信息
    CompanyFundList：提供私募管理人的旗下基金列表
    
    FundBuyInfo：提供【投资-直投产品】列表中公/私募基金的交易记录数据
    FofInvestCustomerPrice：查询直投产品拟合的组合的净值
    FofInvestFundScale：查询直投产品拟合的组合的净值
```


## 安装依赖类库

```shell
    # 进入包含【requirements.txt】文件的目录执行下面命令
    pip install -r requirements.txt --trusted-host mirrors.aliyun.com \
        --index-url "https://mirrors.aliyun.com/pypi/simple/" 
```


## SDK使用示例

```python

    # 将fof99目录添加到Python搜索路径【这步很重要，否则执行脚本找不到请求类】
    import sys
    sys.path.append(r'E:\path\to\mall_sdk')
    
    # 1、引入请求类
    from fof99 import FundPrice
    
    # 2、创建请求对象
    appid = '应用ID，从火富牛API商城获取'
    appkey = '应用密钥，从火富牛API商城获取'
    req = FundPrice(appid, appkey) # 请求对象
    
    # 3、设置请求参数，参考API文档
    req.set_params(reg_code='SN5489', start_date='2024-01-01', order_by='price_date', order=1)
    
    # 4、发起请求， use_df=True表示结果返回pandas.DataFrame对象；use_df=False表示结果返回Python列表
    res = req.do_request(use_df=True)
    
    # 5、结果处理
    print(res) # 打印结果
    print(req.get_debug_info()) # 打印API响应参数，用于接口调试
```

