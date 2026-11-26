# Backtest de estrategia con EMAs en BTC/USDT

Proyecto personal de análisis de datos: probar con datos históricos un método de trading basado en las EMA 21, 50 y 200 en velas diarias.

## Objetivo
Evaluar si mi método (comprar cerca a los tramos cerca de la EMA 21, vender parcialmente en la EMA 50 y cerrar con take profit o stop-loss) rinde mejor que simplemente comprar y mantener BTC.

## Datos
- Fuente: APIs pública de Binance (librería `ccxt`), BTC/USDT diario.
- Periodo: 2018-07-20 a 2026-11-25 (3.252 velas descargadas).
- Costos simulados: comisión de 0,1% por lado y slippage de 0,05%.
- Las órdenes se deciden con el cierre de un día y se ejecutan a la apertura del siguiente, para no usar información del futuro.

## Método
El método usa velas diarias y tres EMAs (21, 50 y 200). Cuando el precio está cerca o por debajo de la EMA 21, el backtester compra pequeños tramos de BTC (el capital se divide en 10 partes). Cuando el precio sube hasta la EMA 50, vende una parte pequeña de lo acumulado para asegurar ganancia. El resto se vende al alcanzar el take profit, definido como un porcentaje sobre el costo promedio. Si el precio cae demasiado por debajo del costo promedio, el stop-loss cierra la posición. La EMA 200 se usa como filtro opcional de tendencia: solo permite comprar si el precio está sobre ella.

## Resultados (capital simulado de 150 USDT)

Los resultados se calculan en porcentaje, por lo que el capital inicial no cambia el retorno (lo verifiqué comparando 1.000 y 150 USDT).

| Corrida | Filtro EMA 200 | Stop | TP | Retorno | Máx. caída | Ciclos (ganadores) |
|---|---|---|---|---|---|---|
| 1 | No | 15% | 15% | +124% | -37,1% | 44 (27) |
| 2 | Sí | 15% | 15% | +71,2% | -41,1% | 27 (18) |
| 3 | Sí | 25% | 15% | +23,1% | -57,6% | 21 (16) |
| 4 | Sí | 15% | 25% | +90,1% | -64,4% | 22 (13) |
| 5 | Sí | 10% | 15% | +11,2% | -37,1% | 33 (17) |
| Referencia | Comprar y mantener | | | +708,3% | -76,6% | |

## Conclusiones
- Ninguna variante le ganó a comprar y mantener en retorno.
- El método redujo la caída máxima en casi todas las corridas, a costa de ganar mucho menos.
- Mi hipótesis era que el filtro EMA 200 protegería contra la caída libre; los datos mostraron lo contrario (+124% sin filtro vs +71% con filtro).
- Un stop más flojo (25%) subió la tasa de acierto (76%) pero bajó el retorno y empeoró la caída máxima: acertar seguido no es lo mismo que ganar más.
- Un stop muy ajustado (10%) sacó al método del mercado por ruido y casi no dejó ganancia.
- La combinación con mejor equilibrio entre retorno y caída fue stop 15% / TP 15%.

## Limitaciones
- Una sola serie histórica (BTC 2018-2026); los resultados pueden no repetirse.
- Seis corridas sobre los mismos datos: hay riesgo de sobreajuste.
- No simula el mínimo de orden de Binance.
- Próximo paso: separar los datos en ajuste y validación, y agregar un gráfico de equity.

## Cómo correrlo
1. Instalar Python 3.12 y las librerías: `pip install ccxt pandas`
2. Ejecutar: `python backtest.py`
3. Los parámetros se editan al inicio de `backtest.py`.

## Autor
Alan, estudiante de Ingeniería de Sistemas.
