import os
import time
import ccxt
import pandas as pd

# ================= PARÁMETROS PROPIOS =================
SYMBOL = "BTC/USDT"
TIMEFRAME = "1d"
START_DATE = "2018-01-01"
INITIAL_CAPITAL = 150.0     # capital inicial en USDT

NEAR_PCT = 0.02              # "cerca" de la EMA 21 = a menos de 2% (o por debajo)
N_TRANCHES = 10              # capital dividido en 10 tramos iguales
PARTIAL_SELL_PCT = 0.20      # al tocar la EMA 50 vende 20% de lo acumulado
TAKE_PROFIT_PCT = 0.15       # vende todo al llegar a +15% sobre costo promedio
STOP_LOSS_PCT = 0.15         # corta si cierra 15% bajo el costo promedio
USE_EMA200_FILTER = True    # True = solo compra si el precio está sobre la EMA 200
COOLDOWN_DAYS = 30           # días sin comprar después de un stop-loss

FEE = 0.001                  # comisión 0.1% por lado
SLIPPAGE = 0.0005            # deslizamiento 0.05%
CSV_CACHE = "btc_1d.csv"
# =============================================================


def download_data():
    if os.path.exists(CSV_CACHE):
        return pd.read_csv(CSV_CACHE, parse_dates=["date"])

    exchange = ccxt.binance({
        "timeout": 30000,
        "options": {"defaultType": "spot", "fetchMarkets": ["spot"]},
    })
    since = exchange.parse8601(START_DATE + "T00:00:00Z")
    rows = []
    while True:
        batch = None
        for attempt in range(5):  # reintenta si la conexión falla
            try:
                batch = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, since=since, limit=1000)
                break
            except Exception as e:
                print(f"Intento {attempt + 1}/5 falló: {type(e).__name__}. Reintentando...")
                time.sleep(3)
        if batch is None:
            raise RuntimeError("No se pudo descargar la data. Revisa tu conexión.")
        if not batch:
            break
        rows += batch
        print(f"Descargadas {len(rows)} velas...")
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(exchange.rateLimit / 1000)

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.drop(columns="ts").drop_duplicates("date")
    df = df.iloc[:-1]  # quita la vela de hoy, que aún no cierra
    df.to_csv(CSV_CACHE, index=False)
    return df


def run_backtest(df):
    df = df.copy()
    for span in (21, 50, 200):
        df[f"ema{span}"] = df["close"].ewm(span=span, adjust=False).mean()
    df = df.iloc[200:].reset_index(drop=True)  # espera a que la EMA 200 tenga historial

    cash = INITIAL_CAPITAL
    btc = 0.0
    pos_cost = 0.0            # USDT gastados en el BTC que aún tienes
    tranche_size = INITIAL_CAPITAL / N_TRANCHES
    tranches_used = 0
    partial_done = False
    cooldown_until = -1
    pending = None            # orden decidida hoy, se ejecuta mañana a la apertura
    cycle_invested = 0.0
    cycle_proceeds = 0.0

    trades, equity, cycles = [], [], []

    for i, row in df.iterrows():
        # 1) Ejecutar la orden decidida en el cierre anterior (sin mirar el futuro)
        if pending is not None:
            kind, reason = pending
            if kind == "buy" and cash >= tranche_size * 0.999 and tranches_used < N_TRANCHES:
                price = row["open"] * (1 + SLIPPAGE)
                spend = min(tranche_size, cash)
                btc += spend * (1 - FEE) / price
                cash -= spend
                pos_cost += spend
                cycle_invested += spend
                tranches_used += 1
                trades.append((row["date"], "BUY", price, spend, reason))
            elif kind in ("partial", "sell_all") and btc > 0:
                frac = PARTIAL_SELL_PCT if kind == "partial" else 1.0
                qty = btc * frac
                price = row["open"] * (1 - SLIPPAGE)
                proceeds = qty * price * (1 - FEE)
                cash += proceeds
                cycle_proceeds += proceeds
                pos_cost *= (1 - frac)
                btc -= qty
                trades.append((row["date"], "SELL", price, proceeds, reason))
                if kind == "partial":
                    partial_done = True
                else:
                    cycles.append(cycle_proceeds - cycle_invested)
                    btc, pos_cost = 0.0, 0.0
                    tranches_used, partial_done = 0, False
                    cycle_invested = cycle_proceeds = 0.0
                    if reason == "stop_loss":
                        cooldown_until = i + COOLDOWN_DAYS
            pending = None

        # 2) Valor de la cuenta al cierre del día
        equity.append((row["date"], cash + btc * row["close"]))

        # 3) Decidir la orden de mañana según el cierre de hoy
        if i == len(df) - 1:
            break
        close = row["close"]
        if btc > 0:
            avg = pos_cost / btc
            if close <= avg * (1 - STOP_LOSS_PCT):
                pending = ("sell_all", "stop_loss")
                continue
            if close >= avg * (1 + TAKE_PROFIT_PCT):
                pending = ("sell_all", "take_profit")
                continue
            if close >= row["ema50"] and not partial_done:
                pending = ("partial", "ema50")
                continue
        near_ema21 = close <= row["ema21"] * (1 + NEAR_PCT)
        trend_ok = (close >= row["ema200"]) if USE_EMA200_FILTER else True
        if near_ema21 and trend_ok and i > cooldown_until and tranches_used < N_TRANCHES \
                and cash >= tranche_size * 0.999:
            pending = ("buy", "near_ema21")

    return df, trades, equity, cycles


def max_drawdown(values):
    s = pd.Series(values)
    return ((s / s.cummax()) - 1).min()


def main():
    df = download_data()
    df, trades, equity, cycles = run_backtest(df)

    eq = pd.DataFrame(equity, columns=["date", "equity"])
    tr = pd.DataFrame(trades, columns=["date", "side", "price", "usdt", "reason"])

    # Comprar y mantener, con las mismas comisiones
    qty_bh = INITIAL_CAPITAL * (1 - FEE) / (df.loc[0, "open"] * (1 + SLIPPAGE))
    eq["buy_hold"] = qty_bh * df["close"]

    final = eq["equity"].iloc[-1]
    final_bh = eq["buy_hold"].iloc[-1]
    wins = sum(1 for c in cycles if c > 0)

    print("=" * 50)
    print(f"Periodo: {df['date'].iloc[0].date()} a {df['date'].iloc[-1].date()}")
    print(f"Capital inicial: {INITIAL_CAPITAL:,.2f} USDT")
    print(f"MÉTODO      -> final {final:,.2f} | retorno {final / INITIAL_CAPITAL - 1:+.1%} "
          f"| máx. caída {max_drawdown(eq['equity']):.1%}")
    print(f"COMPRAR Y MANTENER -> final {final_bh:,.2f} | retorno {final_bh / INITIAL_CAPITAL - 1:+.1%} "
          f"| máx. caída {max_drawdown(eq['buy_hold']):.1%}")
    print(f"Compras: {(tr['side'] == 'BUY').sum()} | Ventas: {(tr['side'] == 'SELL').sum()}")
    print(f"Ciclos cerrados: {len(cycles)} | ganadores: {wins}")
    print("=" * 50)

    tr.to_csv("trades.csv", index=False)
    eq.to_csv("equity.csv", index=False)
    print("Guardé trades.csv y equity.csv (úsalos luego en Power BI).")


if __name__ == "__main__":
    main()