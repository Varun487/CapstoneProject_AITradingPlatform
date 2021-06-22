import pandas as pd

from services.Utils.converter import Converter
from services.Utils.pusher import Pusher
from services.Utils.getters import Getter

from strategies.models import Company
from strategies.models import TickerData
from strategies.models import StrategyType
from strategies.models import StrategyConfig
from strategies.models import Signal
from strategies.models import Order
from strategies.models import Trade

valid_indicators = ['BollingerIndicator']
valid_signal_generators = ['BBSignalGenerator']
valid_take_profit_and_stop_losses = ['TakeProfitAndStopLossBB']
valid_order_executors = ['OrderExecution']
valid_trade_evaluators = ['TradeEvaluator']
valid_companies = ['Company']
valid_strategy_types = ['StrategyType']
valid_strategy_configs = ['StrategyConfig']


def validate_obj(obj, valid_list, db_object=False):
    try:
        if db_object:
            return (obj is not None) and (type(obj).__name__ in valid_list)
        else:
            return (obj is not None) and (obj.__name__ in valid_list)
    except:
        raise ValueError(f"{obj} should be an object in {valid_list}")


class BackTestReportGenerator(object):
    def __init__(self, df=None, ticker_time_period=-1, indicator_time_period=-1, dimension=None, sigma=-1, factor=-1,
                 max_holding_period=-1, company=None, strategy_config=None, strategy_type=None, indicator=None,
                 signal_generator=None, take_profit_stop_loss=None, order_executor=None, trade_evaluator=None):
        self.df = df
        self.ticker_time_period = ticker_time_period
        self.indicator_time_period = indicator_time_period
        self.dimension = dimension
        self.sigma = sigma
        self.factor = factor
        self.max_holding_period = max_holding_period

        self.company = company
        self.strategy_config = strategy_config
        self.strategy_type = strategy_type
        self.indicator = indicator
        self.signal_generator = signal_generator
        self.take_profit_stop_loss = take_profit_stop_loss
        self.order_executor = order_executor
        self.trade_evaluator = trade_evaluator

        self.calc_df = df

        self.valid_df = False
        self.valid_company = False
        self.valid_strategy_type = False
        self.valid_strategy_config = False
        self.valid_indicator = False
        self.valid_signal_generator = False
        self.valid_take_profit_stop_loss = False
        self.valid_order_executor = False
        self.valid_trade_evaluator = False
        self.valid = False

        self.net_returns = 0
        self.net_percent = 0
        self.pf_trades = 0
        self.ls_trades = 0
        self.total_trades = 0
        self.pf_percent = 0
        self.ls_percent = 0

    def validate_df(self):
        self.valid_df = Converter(df=self.df).validate_df() and all(col in self.df.columns for col in
                                                                    ['time_stamp', 'open', 'high', 'low', 'close'])

    def validate(self):
        self.validate_df()
        self.valid_company = validate_obj(self.company, valid_companies, db_object=True)
        self.valid_strategy_type = validate_obj(self.strategy_type, valid_strategy_types, db_object=True)
        self.valid_strategy_config = validate_obj(self.strategy_config, valid_strategy_configs, db_object=True)
        self.valid_indicator = validate_obj(self.indicator, valid_indicators)
        self.valid_signal_generator = validate_obj(self.signal_generator, valid_signal_generators)

        self.valid_take_profit_stop_loss = validate_obj(self.take_profit_stop_loss,
                                                        valid_take_profit_and_stop_losses)

        self.valid_order_executor = validate_obj(self.order_executor, valid_order_executors)
        self.valid_trade_evaluator = validate_obj(self.trade_evaluator, valid_trade_evaluators)

        self.valid = self.valid_df and self.valid_company and self.valid_strategy_type and self.valid_strategy_config \
                     and self.valid_indicator and self.valid_signal_generator \
                     and self.take_profit_stop_loss and self.valid_order_executor and self.valid_trade_evaluator

    def run_backtest(self):
        """Orchestrates calling of services to run back test"""
        # Evaluate all trades
        self.calc_df = self.trade_evaluator(

            # execute orders from signals
            df=self.order_executor(
                max_holding_period=self.max_holding_period,
                dimension=self.dimension,

                # calculate take profit and stop loss prices
                df=self.take_profit_stop_loss(
                    dimension=self.dimension,
                    factor=self.factor,

                    # generate signals
                    df=self.signal_generator(

                        # calculate indicators from input data
                        indicator=self.indicator(
                            df=self.df,
                            time_period=self.indicator_time_period,
                            dimension=self.dimension,
                            sigma=self.sigma,
                        )

                    ).generate_signals()

                ).get_calc_df()

            ).execute()

        ).get_evaluated_df()

    def calc_metrics(self):
        """Calculates metrics based on output of run back test"""

        # Creating a copy of calc_df
        temp_df = self.calc_df.copy()
        temp_df.dropna(inplace=True)

        # Calculating net returns
        self.net_returns = sum(temp_df['trade_net_return'])

        # Calculating Net Return Percent
        self.net_percent = (self.net_returns / sum(temp_df['order_entry_price'])) * 100

        # Calculating total trades
        self.total_trades = len(temp_df)

        # Calculating number of profitable trades
        self.pf_trades = sum(temp_df['trade_net_return'] > 0)

        # Calculating number of loss trades
        self.ls_trades = self.total_trades - self.pf_trades

        # Calculating percentage of profit and loss trades
        self.pf_percent = (self.pf_trades / self.total_trades) * 100
        self.ls_percent = (self.ls_trades / self.total_trades) * 100

    def push_signals(self):
        # pushing signals data
        signals_df = pd.DataFrame()

        signals_df['type'] = ["1" if signal == 'BUY' else "2" for signal in self.calc_df.dropna()['SIGNAL']]
        signals_df['strategy_config'] = [self.strategy_config for i in range(len(self.calc_df.dropna()))]
        signals_df['ticker_data'] = [TickerData.objects.get(time_stamp=time_stamp,
                                                            time_period=self.ticker_time_period,
                                                            company=self.company)
                                     for time_stamp in self.calc_df.dropna().reset_index()['time_stamp']]

        # print(signals_df)
        Pusher(df=signals_df).push(Signal)

        # get signal ids of signals just pushed
        signals_df['signal_id'] = list(Signal.objects.filter(ticker_data__company=self.company,
                                                             strategy_config=self.strategy_config))
        return signals_df

    def push_orders(self):
        pass

    def push_trades(self):
        pass

    def push_backtest_report(self):
        pass

    def push_backtest_trades(self):
        pass

    def push_data(self):
        """Pushes data after calculation of metrics"""
        # push signals data
        signals_df = self.push_signals()

        # push orders data

    def generate_backtest_report(self):
        self.validate()
        if self.valid:
            self.run_backtest()
            self.calc_metrics()
            self.push_data()
            # print(self.calc_df)
        else:
            raise ValueError("Dataframe value given is invalid!")
