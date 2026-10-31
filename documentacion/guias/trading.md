# Trading e inversión (lo que se ve fuera; no es consejo)

## Lo práctico

<!-- guia:inicio (se genera solo: nucleo/reels_destino.py; no editar dentro) -->
Herramientas, estrategias y bots de trading vistos fuera, en una línea cada cosa. Fuentes públicas; nada de esto está probado ni es consejo de inversión.

### Herramientas, datos y plataformas

- **alpha vantage**: Precios históricos y tiempo real de acciones/criptos para backtesting y trading cuantitativo ([fuente](https://alphavantage.co))
- **Astral**: Ejecuta prompts y realiza backtest de bots de trading
- **bureau of labor statistics**: Datos de empleo, nóminas y salarios para construir indicadores económicos
- **Calculators**: Validar cálculos matemáticos, financieros o de unidades y métricas de rendimiento sin hoja de cálculo
- **coingecko**: Precios, volumen y datos on-chain de criptomonedas para screeners y análisis
- **dgtlmoon/changedetection.io**: Vigilar páginas web y notificar cambios en precios, documentación, ofertas de empleo o competidores ([fuente](https://github.com/dgtlmoon/changedetection.io))
- **Discord**: Unirse al grupo gratuito para ver jugadas de trading del creador
- **eia**: Datos de petróleo, gas y electricidad para correlacionar con activos financieros
- **FORECAST**: Análisis cuantitativo de precios y escenarios de trading con rangos de previsión, alternativa gratuita a terminal Bloomberg
- **fred**: Series macroeconómicas (tipos, inflación, desempleo) para modelos cuantitativos
- **JPMorgan Chase Quantitative Research Virtual Job Simulation**: Aprender flujos de trabajo de quantitative research reales y añadir certificado oficial de JPMorgan al CV
- **Polyfly**: Polyfly recibe una captura de una apuesta y genera investigación automática sobre el mercado; puede integrarse vía API o scraping para apoyar decisiones de inversión en Polymarket ([fuente](https://polifly.io))
- **Polymarket**: Analizar datos de mercados de predicción para estrategias de trading cuantitativo
- **rainbow-me/rainbow**: Cómo integrar una wallet Ethereum (firma, conexión, UI) en React Native para funciones crypto/trading en NEXO ([fuente](https://github.com/rainbow-me/rainbow))
- **Statistical Arbitrage Simplified: Essential Strategies and Risks (Investopedia, James Chen)**: Artículo de Investopedia sobre estrategias y riesgos del arbitraje estadístico. Útil como base teórica para documentar implementación: cubre pares correlacionados, cointegración, gestión de riesgo y riesgos de modelo
- **The Pre-FOMC Announcement Drift**: Paper candidato (2012) hallado por busqueda publica (crossref, por titulo), sin verificar que sea el del vídeo ([fuente](https://doi.org/10.2139/ssrn.2024459))
- **The Psychology of Money**: Internalizar principios de finanzas conductuales para tomar decisiones de inversión racionales y construir riqueza a largo plazo
- **thehustleblower.com**: Descubrir side hustles reales filtrados por horas, coste inicial y ganancias reportadas ([fuente](https://thehustleblower.com))

### Estrategias y técnicas

- **24-hour slices**: Divide series temporales en intervalos fijos de 24h para aislar efectos de eventos puntuales (ej. anuncios Fed) promediando retornos por ventana; aplicable a backtesting de estrategias event-driven
- **Cumulative Excess Return with Cost**: Métrica para comparar el desempeño de estrategias contra un benchmark neto de costes en trading cuantitativo con NEXO
- **Cumulative Return with Cost**: Métrica para evaluar el rendimiento neto de estrategias de trading en backtests de NEXO contabilizando costes operativos
- **high-frequency trading (HFT)**: Trading style that uses powerful computers to execute a large number of orders at very high speeds
- **Kelly criterion**: Para dimensionar posiciones de manera óptima, primero estima la probabilidad de éxito (p) y la relación riesgo‑beneficio (B). La fórmula de Kelly: (p*(B+1)-1)/B². Ajusta el resultado al capital disponible y aplica un margen de seguridad para evitar sobreaprovechamiento
- **law of large numbers**: Al incrementar el número de operaciones, la media de resultados converge al valor esperado, reduciendo la varianza del rendimiento mensual
- **movimiento de velas**: El modelo FORECAST se entrena con la forma y secuencia temporal de velas (price action crudo OHLC). Para replicar o usar este enfoque, alimentar al modelo con secuencias de velas normalizadas, no solo indicadores derivados, permitiendo que aprenda patrones de movimiento directo
- **simple '5/10' strategy**: Regla: comprar $5 de una acción que haya caído 5 % en la última semana y vender $10 de otra que haya subido 10 % en la misma semana. Repetir simultáneamente en ~4 500 símbolos para diversificar
- **statistical arbitrage**: Aprovechar ineficiencias de precios entre muchos activos mediante posiciones largas y cortas simultáneas, buscando retornos promedio positivos
- **Statistical Arbitrage (Pairs Trading)**: Estrategia de pairs trading: comprar rezagado, vender líder en pares correlacionados, apostando a reversión a la media del spread. Objetivo: implementar módulo en NEXO con detección de cointegración y ejecución automática
- **Zero-shot forecasting con intervalos de confianza**: Usar TimesFM para obtener pronósticos e intervalos de confianza (best/worst case) sin fine-tuning, útil para decisiones de trading o negocio donde la incertidumbre importa

### Bots e ideas de bots

- **AI Research & Intelligence**: Cómo arquitectar un sistema multi-agente que monitorice crypto, acciones, lanzamientos de competidores y precios de APIs/cloud y entregue solo señales accionables (no ruido) en tiempo real
- **All-Asset Trend Portfolio**: Cartera de tendencia multi-activo de 7 tramos puntuando cada tramo en multiples marcos temporales
- **Boss Bot (regime rotation)**: Bot de ramificacion de régimen para alternar entre estrategias de tendencia y reversion a la media segun la volatilidad
- **Cobertura como startup de IA o hedge fund apalancado**: Sugerencia en broma de que el falso empleo se pueda vender como experiencia en IA o trading cuantitativo
- **Confluence Signal Bot**: Bot de confluencia N de M que define reglas, dimensiona posicion y prueba con datos reales
- **Daily Chaser (rotation)**: Bot de rotacion diaria top-N a traves de un universo definido con re-puntuacion y coste de rotacion
- **Daily Trend (BTC)**: Bot de tendencia diaria Turtle 20/10 mas EMA 10/30 en Bitcoin
- **Equilibrium / Z-Score Bot**: Bot de equilibrio por z-score en un activo para decidir reversion a la media o continuacion usando datos reales
- **Forex University**: Curso comunitario gratuito sin login que cubre fundamentos de trading cuantitativo hasta financiación ([fuente](https://perchance.org/ug0ux99u8f))
- **Hosting web simple**: Levanta nginx/Caddy en la Pi para servir dashboards de NEXO, APIs locales (Ollama) o paneles de trading en LAN con HTTPS automático (Caddy) sin depender de nube
- **Master Allocator**: Estrategia para agrupar estrategias guardadas por clase de activo, puntuar en 5 marcos temporales y asignar capital continuamente con stop loss del sistema
- **Modulo NEXO de Pairs Trading: deteccion de cointegracion, generacion de senales, backtesting…**: Cómo diseñar pipeline completo de statistical arbitrage en NEXO: universo de pares, tests Engle-Granger/Johansen, z-score spread, position sizing, bracket orders, integración con Ollama/Gemini y broker API
- **Prop-Firm Constrained Bot**: Bot disenado bajo reglas de cuentas de fondeo con perdida diaria maxima, ratio riesgo-beneficio minimo y perdida maxima de cierre
- **Risk-Off Overlay**: Capa de mitigacion de riesgo de mercado para estrategias existentes con trailing stop y recorte de exposicion
- **RSI-2 Mean Reversion (SPY)**: Bot de reversion a la media con RSI-2 en SPY con test walk-forward de barras diarias
- **Sensores ambientales (temperatura, humedad, CO₂, etc.)**: Conecta sensores I2C/GPIO (BME280, SCD41) a la Pi, guarda datos en InfluxDB/Grafana para correlacionar temperatura/CO₂ con rendimiento de inferencia local y salud del rack

### Consejos

- **Avoid the Noise**: No intentar competir con algoritmos HFT; centrarse en tendencias más amplias y evitar micro‑movimientos de ruido
- **Focus on Higher Timeframes**: Preferir marcos temporales de días, semanas o meses; así se reduce la exposición a la velocidad de los bots de alta frecuencia
- **How Money Works**: Entiende cómo funciona el dinero: no solo ganar, sino guardar, invertir y hacerlo crecer; evita errores financieros tempranos en tu carrera tech
- **Use Limit Orders**: Utilizar órdenes limitadas para fijar precios de entrada y salida, evitando que los sistemas HFT capturen el spread completo

### Proyectos, datos y otros

- **6O TRADINGDAYS**: Ventana de referencia: usar 60 días de trading para estimar la media y desviación típica del spread
- **A Limit Order Book Market-Making Simulator**: Implementa un simulador de limit order book donde cotices bid/ask, captures spread y gestiones riesgo de inventario, skill clave para market makers como Jane Street u Optiver
- **A Machine Learning Alpha Signal**: Entrena un modelo ML para predecir retornos usando walk-forward validation y prevención estricta de data leakage, evidenciando rigor científico frente al overfitting financiero
- **A Pairs Trading Backtester**: Desarrolla un backtester de pairs trading basado en cointegración incluyendo costes de transacción y validación out-of-sample para simular mean-reversion sin overfitting
- **An Options Pricing and Greeks Engine**: Construye un motor de precios de opciones y griegas (Black-Scholes, binomiales, Monte Carlo) con datos reales para demostrar dominio matemático de derivados y superficie de volatilidad implícita
- **AWS Educate**: Desplegar modelos NEXO en nube híbrida y practicar infra para trading cuantitativo
- **CASH OUT BET**: Señal de salida: cerrar la posición cuando el spread regresa a su media (convergencia)
- **Coke/Pepsi pair trade 1972-2020: +46,000% (laggard/leader) vs -99% (leader/laggard)**: Backtest 1972-2020 Coke/Pepsi: +46,000% comprando rezagado/vendiendo líder vs -99% inversa. Validación histórica de la estrategia
- **Data Analysis with Python**: Aplicar análisis de datos a datasets de trading cuantitativo y telemetría de NEXO; certificado IBM para CV
- **Google Advanced Data Analytics**: Desarrollar habilidades de análisis cuantitativo para trading algorítmico y métricas de NEXO
- **Google Data Analytics Professional Certificate**: Acreditar competencias en análisis de datos con Excel, SQL y visualización
- **Google Machine Learning Crash Course**: Entender fundamentos de ML/LLM para mejorar orquestación de modelos locales y APIs en NEXO y trading cuantitativo
- **GTA VI Extended Look day 1 views 15-20M**: Mercado sobre las visualizaciones del tráiler extendido de GTA VI; sirve como ejemplo de evento a monitorizar y analizar con Polyfly
- **Investment Banking Virtual Internship**: Programa de pasantía virtual gratuita de banca de inversión con certificación para roles en finanzas corporativas y mercados de capitales
- **ITS OWN BLEND**: Cada acción tiene una 'familia' única de 15 patrones de cointegración que explica ~50% de sus movimientos; el resto es ruido idiosincrásico
- **MongoDB Associate Developer**: Usar MongoDB como BD local/embebida para NEXO (chats, embeddings, logs trading)
- **Pares correlacionados listados: KO/PEP, WMT/TGT, HD/LOW, XOM/CVX, UPS/FDX, F/GM, DAL/UAL, LMT/NOC,…**: Lista de 19 pares de tickers correlacionados (KO/PEP, WMT/TGT, HD/LOW, XOM/CVX, UPS/FDX, F/GM, DAL/UAL, LMT/NOC, NKE/UAA, PFE/MRK, GS/MS, INTC/AMD, COST/BJ, UBER/LYFT, VZ/T, MAR/HLT, CAT/DE, NFLX/DIS, IR/A) para universe de pairs trading
- **Past one and a quarter**: Umbral de entrada: abrir posición cuando la desviación del spread supera 1.25 veces su desviación estándar histórica (ventana 60 días)
- **Perderse los 8 días más importantes del mercado en un año, y te habrías perdido el 80% de sus…**: 
- **Power BI**: Crear dashboards de métricas de trading cuantitativo y monitorizar estrategias
- **Quantitative Research Virtual Internship**: Pasantía virtual gratuita de investigación cuantitativa con certificación de JP Morgan para desarrollar habilidades en trading cuantitativo y modelado financiero
- **Resultados cerrados con ganancia (France 72%, Portugal 28%, Argentina 74%)**: Capturas de apuestas resueltas en Polymarket mostrando beneficios (ej. +$798, +$953, +$1332)
- **S&P 500**: Índice bursátil que agrupa a las 500 mayores empresas de EE.UU
- **Segmentos de cliente del ejemplo**: Tres segmentos con share e ingresos: Early-career (45%, $38-85k), Mid-career (40%, $85-150k), High earner (15%, $150-210k). Patrón aplicable a modelado de usuarios en NEXO o trading cuantitativo
- **Snowflake University Hands-on Essentials**: Analizar datos trading a escala; compartir datasets con NEXO para backtesting
- **the paper**: Estudio académico que documenta el efecto de los anuncios de la Reserva Federal en los rendimientos del S&P 500
- **Tres webs dan acceso gratis a todo: streaming ilimitado, IA premium (GPT-6, Claude) y análisis…**:
<!-- guia:fin -->

## Investigaciones

<!-- investigaciones:inicio (se genera solo: nucleo/reels_destino.py; no editar dentro) -->
Investigaciones de trading (tareas con la etiqueta `tema:trading`). Se hacen como las demás, pero su resultado se queda aquí: no van a NEXO ni al despiece de integraciones.

- **T1032** Investigar: 60 Minutes (hecha): RESULTADO DESCARTAR, 60 Minutes es contenido audiovisual de CBS con terminos que restringen la extraccion automatizada; no es una herramienta para NEXO, solo una fuente de transcripciones puntual
- **T1033** Investigar: high-speed computer (hecha): RESULTADO DESCARTAR, No existe un producto o servicio único verificable con ese nombre que pueda adoptarse tal cual para NEXO
- **T1057** Investigar: Daily Chaser (rotation) (propuesta)
- **T1059** Investigar: Master Allocator (propuesta)
- **T1060** Investigar: Prop-Firm Constrained Bot (propuesta)
- **T1061** Investigar: Confluence Signal Bot (propuesta)
- **T1062** Investigar: Equilibrium / Z-Score Bot (propuesta)
- **T1063** Investigar: Risk-Off Overlay (propuesta)
- **T1064** Investigar: Daily Trend (BTC) (propuesta)
- **T1065** Investigar: RSI-2 Mean Reversion (SPY) (propuesta)
- **T1066** Investigar: All-Asset Trend Portfolio (propuesta)
- **T1067** Investigar: Boss Bot (regime rotation) (propuesta)
- **T1068** Investigar: rainbow-me/rainbow (propuesta)
<!-- investigaciones:fin -->
