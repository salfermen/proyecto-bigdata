"""Configuración compartida del pipeline medallón (Bronce -> Plata) para AMLSim."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_BRONCE = RAIZ / "data" / "bronce"
DIR_FUENTE = DIR_BRONCE / "_fuente"          # archivos .tgz tal como se descargan
DIR_PLATA = RAIZ / "data" / "plata"
DIR_REPORTES = RAIZ / "reportes"

# Fuente oficial: repositorio IBM/AMLSim (rama master), carpeta sample/
URL_BASE = "https://raw.githubusercontent.com/IBM/AMLSim/master/sample"

# Escenarios de simulación publicados por IBM. Todos comparten la misma población
# de 20.000 cuentas; cambia la tipología de lavado inyectada.
ESCENARIOS = {
    "20K_fanin200cycle200": "200 patrones fan-in (pitufeo) + 200 ciclos (triangulación)",
    "20K_fanin200": "200 patrones fan-in (pitufeo)",
    "20K_cycle200": "200 patrones de ciclo (triangulación)",
}
ESCENARIO_PRINCIPAL = "20K_fanin200cycle200"

# AMLSim define en conf.json "base_date": "2017-01-01" y cada paso (step) = 1 día.
FECHA_BASE = "2017-01-01"

# Esquema esperado en Bronce (nombres originales del simulador)
COLS_CUENTAS_BRONCE = ["nodeid", "isFraud", "init_balance", "fraudStep"]
COLS_TX_BRONCE = ["sourceNodeId", "targetNodeId", "value", "time"]

# Renombrado a nombres de negocio en Plata
RENOMBRE_CUENTAS = {
    "nodeid": "cuenta_id",
    "isFraud": "es_fraude",
    "init_balance": "saldo_inicial",
    "fraudStep": "paso_fraude",
}
RENOMBRE_TX = {
    "sourceNodeId": "cuenta_origen",
    "targetNodeId": "cuenta_destino",
    "value": "monto",
    "time": "paso",
}

CENTINELA_SIN_PASO = -1   # AMLSim usa -1 para "sin paso de fraude registrado"
