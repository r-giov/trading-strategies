//+------------------------------------------------------------------+
//|                                          QS_MACD_Crossover.mq5   |
//|                                    QS Finance Trading Platform    |
//|                                                                    |
//| MACD Crossover Strategy — matches notebook signal logic exactly   |
//| Signal: MACD line crosses signal line                              |
//| Entry: On next bar after crossover (1-bar delay built into EA)    |
//| Exit: Opposite crossover                                           |
//| Compatible with FTMO Strategy Tester for tick-level backtesting   |
//+------------------------------------------------------------------+
#property copyright "QS Finance"
#property version   "1.00"
#property strict

//--- Input parameters (match notebook grid search ranges)
input int    FastPeriod     = 12;       // MACD Fast Period (8-30)
input int    SlowPeriod     = 26;       // MACD Slow Period (20-60)
input int    SignalPeriod   = 9;        // MACD Signal Period (3-15)
input double RiskPercent    = 2.0;      // Risk per trade (% of equity)
input double FixedLots      = 0.0;     // Fixed lot size (0 = use risk%)
input int    MagicNumber    = 240308;   // Magic number for order identification
input bool   LongOnly       = true;     // Long-only mode (FTMO crypto)

//--- FTMO Risk Management
input double MaxDailyLossPct  = 4.0;   // Max daily loss % (FTMO: 5%, buffer: 4%)
input double MaxTotalLossPct  = 8.0;   // Max total loss % (FTMO: 10%, buffer: 8%)

//--- Internal variables
int macdHandle;
double macdBuffer[];
double signalBuffer[];
double histBuffer[];
double startBalance;
double dayStartEquity;
datetime lastDayCheck;

//+------------------------------------------------------------------+
int OnInit()
{
   macdHandle = iMACD(_Symbol, PERIOD_CURRENT, FastPeriod, SlowPeriod, SignalPeriod, PRICE_CLOSE);
   if(macdHandle == INVALID_HANDLE)
   {
      Print("Failed to create MACD indicator");
      return INIT_FAILED;
   }

   ArraySetAsSeries(macdBuffer, true);
   ArraySetAsSeries(signalBuffer, true);
   ArraySetAsSeries(histBuffer, true);

   startBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   lastDayCheck = 0;

   Print("QS MACD Crossover initialized | ", _Symbol,
         " | Fast=", FastPeriod, " Slow=", SlowPeriod, " Signal=", SignalPeriod);

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(macdHandle != INVALID_HANDLE)
      IndicatorRelease(macdHandle);
}

//+------------------------------------------------------------------+
void OnTick()
{
   //--- Only trade on new bar (daily timeframe = once per day)
   static datetime lastBar = 0;
   datetime currentBar = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(currentBar == lastBar) return;
   lastBar = currentBar;

   //--- FTMO risk check
   if(!CheckFTMORisk()) return;

   //--- Get MACD values (bar[1] = last completed bar, bar[2] = bar before)
   if(CopyBuffer(macdHandle, 0, 0, 3, macdBuffer) < 3) return;
   if(CopyBuffer(macdHandle, 1, 0, 3, signalBuffer) < 3) return;

   // Previous completed bar values (shift 1 = execution delay)
   double prevMACD   = macdBuffer[2];
   double currMACD   = macdBuffer[1];
   double prevSignal = signalBuffer[2];
   double currSignal = signalBuffer[1];

   //--- Signal logic (exact match to notebook)
   bool buySignal  = (prevMACD <= prevSignal) && (currMACD > currSignal);
   bool sellSignal = (prevMACD >= prevSignal) && (currMACD < currSignal);

   //--- Check current position
   int posType = GetPositionType();

   //--- Execute signals
   if(buySignal && posType != POSITION_TYPE_BUY)
   {
      if(posType == POSITION_TYPE_SELL && !LongOnly)
         ClosePosition();
      OpenPosition(ORDER_TYPE_BUY);
   }
   else if(sellSignal)
   {
      if(posType == POSITION_TYPE_BUY)
         ClosePosition();
      // Only open short if not long-only mode
      if(!LongOnly && posType != POSITION_TYPE_SELL)
         OpenPosition(ORDER_TYPE_SELL);
   }
}

//+------------------------------------------------------------------+
bool CheckFTMORisk()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);

   // Reset day start equity at new day
   MqlDateTime dt;
   TimeCurrent(dt);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d", dt.year, dt.mon, dt.day));
   if(today != lastDayCheck)
   {
      dayStartEquity = equity;
      lastDayCheck = today;
   }

   // Daily loss check
   double dailyLoss = (dayStartEquity - equity) / startBalance * 100;
   if(dailyLoss >= MaxDailyLossPct)
   {
      Print("FTMO DAILY LOSS LIMIT: ", DoubleToString(dailyLoss, 2), "% — STOP TRADING");
      return false;
   }

   // Total loss check
   double totalLoss = (startBalance - equity) / startBalance * 100;
   if(totalLoss >= MaxTotalLossPct)
   {
      Print("FTMO TOTAL LOSS LIMIT: ", DoubleToString(totalLoss, 2), "% — STOP TRADING");
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
int GetPositionType()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         return (int)PositionGetInteger(POSITION_TYPE);
   }
   return -1; // No position
}

//+------------------------------------------------------------------+
double CalculateLotSize(ENUM_ORDER_TYPE orderType)
{
   if(FixedLots > 0) return FixedLots;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double riskAmount = equity * RiskPercent / 100.0;

   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   // Simple position sizing based on risk
   double price = (orderType == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double lots = riskAmount / (price * tickValue / tickSize);
   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(minLot, MathMin(maxLot, lots));

   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
void OpenPosition(ENUM_ORDER_TYPE orderType)
{
   double price = (orderType == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lots = CalculateLotSize(orderType);

   MqlTradeRequest request = {};
   MqlTradeResult result = {};

   request.action   = TRADE_ACTION_DEAL;
   request.symbol   = _Symbol;
   request.volume   = lots;
   request.type     = orderType;
   request.price    = price;
   request.deviation = 20;
   request.magic    = MagicNumber;
   request.comment  = "QS_MACD_" + _Symbol;
   request.type_filling = ORDER_FILLING_IOC;

   if(OrderSend(request, result))
   {
      string dir = (orderType == ORDER_TYPE_BUY) ? "BUY" : "SELL";
      Print("OPENED ", dir, " ", lots, " ", _Symbol, " @ ", result.price,
            " | MACD[1]=", DoubleToString(macdBuffer[1], 6),
            " Signal[1]=", DoubleToString(signalBuffer[1], 6));
   }
   else
   {
      Print("Order failed: ", result.comment, " (", result.retcode, ")");
   }
}

//+------------------------------------------------------------------+
void ClosePosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
      {
         ulong ticket = PositionGetInteger(POSITION_TICKET);
         double volume = PositionGetDouble(POSITION_VOLUME);
         ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

         ENUM_ORDER_TYPE closeType = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
         double price = (closeType == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);

         MqlTradeRequest request = {};
         MqlTradeResult result = {};

         request.action   = TRADE_ACTION_DEAL;
         request.symbol   = _Symbol;
         request.volume   = volume;
         request.type     = closeType;
         request.position = ticket;
         request.price    = price;
         request.deviation = 20;
         request.magic    = MagicNumber;
         request.comment  = "QS_MACD_CLOSE";
         request.type_filling = ORDER_FILLING_IOC;

         if(OrderSend(request, result))
         {
            double profit = PositionGetDouble(POSITION_PROFIT);
            Print("CLOSED ", _Symbol, " @ ", result.price, " | P&L: $", DoubleToString(profit, 2));
         }
      }
   }
}
//+------------------------------------------------------------------+
