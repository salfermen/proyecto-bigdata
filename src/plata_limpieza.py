"""Capa PLATA: limpieza, tipado, validación y conformación de AMLSim.

Entrada : data/bronce/<escenario>/{nodes.csv, transactions.csv}   (crudo, inmutable)
Salida  : data/plata/cuentas.parquet
          data/plata/transacciones.parquet
          data/plata/cuarentena_cuentas.parquet
          data/plata/cuarentena_transacciones.parquet
          data/plata/csv/*.csv                      (copias para revisión)
          data/plata/_reporte_calidad_plata.json    (métricas, reglas y validaciones)

Principios:
  * Nada se borra en silencio: todo registro rechazado va a cuarentena con su motivo.
  * Cada regla deja un conteo, y al final se concilia Bronce = Plata + cuarentena.
  * Si una validación posterior falla, el proceso termina con error (código 1).

Uso:  python src/plata_limpieza.py
"""
import json
import re
import sys

import numpy as np
import pandas as pd

from config import (CENTINELA_SIN_PASO, COLS_CUENTAS_BRONCE, COLS_TX_BRONCE,
                    DIR_BRONCE, DIR_PLATA, ESCENARIOS, FECHA_BASE,
                    RENOMBRE_CUENTAS, RENOMBRE_TX)

FECHA_PROCESO = pd.Timestamp.now(tz="UTC").floor("s")
F_BASE = pd.Timestamp(FECHA_BASE)


# --------------------------------------------------------------------------- utilidades
def leer_bronce(esc, archivo, columnas):
    """Lee el CSV crudo TODO como texto (sin inferencia) para controlar el tipado."""
    ruta = DIR_BRONCE / esc / archivo
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    faltantes = set(columnas) - set(df.columns)
    if faltantes:
        raise ValueError(f"{ruta}: faltan columnas {faltantes}")
    df = df[columnas].apply(lambda s: s.str.strip())
    df.insert(0, "escenario", esc)
    df["fila_bronce"] = np.arange(2, len(df) + 2)  # línea en el archivo (1 = encabezado)
    return df


def separar(df, motivo, crudo, regla):
    """Divide df en (válidos, rechazados). Los rechazados conservan el valor crudo."""
    malo = motivo.ne("")
    rech = crudo.loc[df.index[malo]].copy()
    rech["regla"] = regla
    rech["motivo"] = motivo[malo].str.rstrip(";")
    return df.loc[~malo].copy(), rech


def tipar(df, esquema, crudo, regla):
    """Convierte columnas a numérico; vacíos y no convertibles van a cuarentena."""
    motivo = pd.Series("", index=df.index, dtype=object)
    for col, tipo in esquema.items():
        vacio = df[col].eq("")
        num = pd.to_numeric(df[col].where(~vacio), errors="coerce")
        invalido = ~vacio & num.isna()
        if tipo == "int":
            invalido |= num.notna() & (num % 1 != 0)
        motivo[vacio] += f"nulo:{col};"
        motivo[invalido] += f"tipo_invalido:{col};"
        df[col] = num
    return separar(df, motivo, crudo, regla)


def parsear_metadata(esc):
    ruta = DIR_BRONCE / esc / "metadata.txt"
    texto = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
    m_f = re.search(r"\((\d[\d,]*) fraud nodes\)", texto)
    m_t = re.search(r"transactions:\s*([\d,]+)", texto)
    a_int = lambda m: int(m.group(1).replace(",", "")) if m else None
    return {"fraude_declarado": a_int(m_f), "tx_declaradas": a_int(m_t)}


# --------------------------------------------------------------------------- cuentas
def limpiar_cuentas(esc):
    crudo = leer_bronce(esc, "nodes.csv", COLS_CUENTAS_BRONCE)
    met = {"filas_bronce": len(crudo)}
    rechazos = []
    df = crudo.rename(columns=RENOMBRE_CUENTAS)

    # C1 - tipado y nulos
    df, r = tipar(df, {"cuenta_id": "int", "es_fraude": "int",
                       "saldo_inicial": "float", "paso_fraude": "int"}, crudo, "C1_tipado_nulos")
    rechazos.append(r); met["C1_tipado_nulos"] = len(r)

    # C2 - dominio de valores
    motivo = pd.Series("", index=df.index, dtype=object)
    motivo[df.cuenta_id < 0] += "cuenta_id_negativo;"
    motivo[~df.es_fraude.isin([0, 1])] += "es_fraude_fuera_de_dominio;"
    motivo[df.saldo_inicial < 0] += "saldo_inicial_negativo;"
    motivo[df.paso_fraude < CENTINELA_SIN_PASO] += "paso_fraude_invalido;"
    df, r = separar(df, motivo, crudo, "C2_dominio")
    rechazos.append(r); met["C2_dominio"] = len(r)

    # C3 - unicidad de la llave (escenario, cuenta_id)
    dup = df.duplicated("cuenta_id", keep="first")
    motivo = pd.Series(np.where(dup, "cuenta_id_duplicada", ""), index=df.index)
    df, r = separar(df, motivo, crudo, "C3_llave_duplicada")
    rechazos.append(r); met["C3_llave_duplicada"] = len(r)

    # C4 - centinela -1 => nulo (dato faltante explícito, no un número)
    es_centinela = df.paso_fraude.eq(CENTINELA_SIN_PASO)
    met["C4_centinela_a_nulo"] = int(es_centinela.sum())
    df["paso_fraude"] = df.paso_fraude.mask(es_centinela)

    # C5 - consistencia: una cuenta NO fraudulenta no puede tener paso de fraude
    inconsistente = df.es_fraude.eq(0) & df.paso_fraude.notna()
    met["C5_paso_en_no_fraude_corregido"] = int(inconsistente.sum())
    df.loc[inconsistente, "paso_fraude"] = np.nan

    # Tipos finales y columnas derivadas
    df = df.assign(
        cuenta_id=df.cuenta_id.astype("int32"),
        es_fraude=df.es_fraude.astype("int8"),
        saldo_inicial=df.saldo_inicial.round(2),
        paso_fraude=df.paso_fraude.astype("Int16"),
    )
    df["paso_fraude_registrado"] = df.paso_fraude.notna()
    df["fecha_fraude"] = (F_BASE + pd.to_timedelta(df.paso_fraude.astype("float"), unit="D")).dt.date
    met["filas_plata"] = len(df)
    return df, pd.concat(rechazos, ignore_index=True), met


# --------------------------------------------------------------------------- transacciones
def limpiar_transacciones(esc, cuentas):
    crudo = leer_bronce(esc, "transactions.csv", COLS_TX_BRONCE)
    met = {"filas_bronce": len(crudo)}
    rechazos = []
    df = crudo.rename(columns=RENOMBRE_TX)

    # T1 - tipado y nulos
    df, r = tipar(df, {"cuenta_origen": "int", "cuenta_destino": "int",
                       "monto": "float", "paso": "int"}, crudo, "T1_tipado_nulos")
    rechazos.append(r); met["T1_tipado_nulos"] = len(r)

    # T2 - dominio: monto positivo y paso de simulación válido
    motivo = pd.Series("", index=df.index, dtype=object)
    motivo[df.monto <= 0] += "monto_no_positivo;"
    motivo[df.paso < 1] += "paso_invalido;"
    df, r = separar(df, motivo, crudo, "T2_dominio")
    rechazos.append(r); met["T2_dominio"] = len(r)

    # T3 - integridad referencial contra las cuentas limpias del mismo escenario
    validas = set(cuentas.cuenta_id)
    motivo = pd.Series("", index=df.index, dtype=object)
    motivo[~df.cuenta_origen.isin(validas)] += "cuenta_origen_inexistente;"
    motivo[~df.cuenta_destino.isin(validas)] += "cuenta_destino_inexistente;"
    df, r = separar(df, motivo, crudo, "T3_integridad_referencial")
    rechazos.append(r); met["T3_integridad_referencial"] = len(r)

    # T4 - autotransferencias (origen = destino): no son movimientos entre contrapartes
    motivo = pd.Series(np.where(df.cuenta_origen.eq(df.cuenta_destino), "autotransferencia", ""), index=df.index)
    df, r = separar(df, motivo, crudo, "T4_autotransferencia")
    rechazos.append(r); met["T4_autotransferencia"] = len(r)

    # T5 - duplicados exactos (mismo origen, destino, paso y monto al centavo).
    # El dataset no trae ID de transacción, así que no se puede probar que sean eventos
    # distintos. Se colapsan a una fila y se conserva el conteo en n_registros_origen
    # (reversible y sin perder la señal para la capa Oro).
    df["monto_centavos"] = (df.monto * 100).round().astype("int64")
    llave = ["cuenta_origen", "cuenta_destino", "paso", "monto_centavos"]
    df = (df.groupby(llave, sort=False, as_index=False)
            .agg(escenario=("escenario", "first"),
                 fila_bronce=("fila_bronce", "min"),
                 n_registros_origen=("fila_bronce", "size")))
    met["T5_duplicados_colapsados"] = int((df.n_registros_origen - 1).sum())
    met["T5_grupos_con_duplicado"] = int((df.n_registros_origen > 1).sum())

    # Tipos finales y columnas derivadas
    df = df.assign(
        cuenta_origen=df.cuenta_origen.astype("int32"),
        cuenta_destino=df.cuenta_destino.astype("int32"),
        monto=df.monto_centavos / 100,
        paso=df.paso.astype("int16"),
        n_registros_origen=df.n_registros_origen.astype("int16"),
    ).drop(columns="monto_centavos")
    df["fecha"] = (F_BASE + pd.to_timedelta(df.paso.astype("int64"), unit="D")).dt.date
    df = df.sort_values(["paso", "cuenta_origen", "cuenta_destino", "monto"], kind="stable")
    met["filas_plata"] = len(df)
    return df, pd.concat(rechazos, ignore_index=True), met


# --------------------------------------------------------------------------- observaciones
def observar(esc, cuentas, tx, rech_tx, met_tx):
    """Hallazgos que NO se corrigen en Plata pero deben conocerse antes de Oro."""
    fraude = set(cuentas.loc[cuentas.es_fraude.eq(1), "cuenta_id"])
    entre_fraude = tx.cuenta_origen.isin(fraude) & tx.cuenta_destino.isin(fraude)
    tx_ff = tx[entre_fraude]
    con_tx_ff = set(tx_ff.cuenta_origen) | set(tx_ff.cuenta_destino)
    meta = parsear_metadata(esc)
    dups = tx[tx.n_registros_origen > 1]
    auto = rech_tx[rech_tx.regla.eq("T4_autotransferencia")]
    auto_ff = auto.sourceNodeId.astype(int).isin(fraude).sum() if len(auto) else 0
    menor_100 = tx.monto < 100
    return {
        "metadata_fraude_declarado": meta["fraude_declarado"],
        "fraude_observado": len(fraude),
        "metadata_tx_declaradas": meta["tx_declaradas"],
        "tx_bronce_observadas": met_tx["filas_bronce"],
        "pct_cuentas_fraude": round(100 * len(fraude) / len(cuentas), 2),
        "cuentas_fraude_sin_paso_registrado": int((cuentas.es_fraude.eq(1) & ~cuentas.paso_fraude_registrado).sum()),
        "cuentas_fraude_sin_tx_con_otra_fraude": len(fraude - con_tx_ff),
        "cuentas_sin_transacciones": int((~cuentas.tiene_transacciones).sum()),
        "tx_entre_cuentas_fraude": int(entre_fraude.sum()),
        "pct_tx_entre_cuentas_fraude": round(100 * entre_fraude.mean(), 2),
        "grupos_duplicados_entre_cuentas_fraude": int((dups.cuenta_origen.isin(fraude) & dups.cuenta_destino.isin(fraude)).sum()),
        "grupos_duplicados_total": len(dups),
        "autotransferencias_de_cuentas_fraude": int(auto_ff),
        "tx_monto_menor_100": int(menor_100.sum()),
        "pct_tx_monto_menor_100_entre_fraude": round(100 * entre_fraude[menor_100].mean(), 2) if menor_100.any() else None,
        "monto_minimo_tx_no_fraude": float(tx.loc[~entre_fraude, "monto"].min()),
        "monto_min": float(tx.monto.min()), "monto_max": float(tx.monto.max()),
        "paso_min": int(tx.paso.min()), "paso_max": int(tx.paso.max()),
        "fecha_min": str(tx.fecha.min()), "fecha_max": str(tx.fecha.max()),
    }


# --------------------------------------------------------------------------- validación
def validar(cuentas, tx, metricas):
    """Contrato de datos de la capa Plata. Devuelve una lista de chequeos."""
    chk = []

    def regla(id_, tabla, desc, violaciones):
        chk.append({"id": id_, "tabla": tabla, "descripcion": desc,
                    "violaciones": int(violaciones), "ok": int(violaciones) == 0})

    req_c = ["escenario", "cuenta_id", "es_fraude", "saldo_inicial"]
    req_t = ["tx_id", "escenario", "cuenta_origen", "cuenta_destino", "monto", "paso", "fecha"]
    regla("V01", "cuentas", "Llave (escenario, cuenta_id) única", cuentas.duplicated(["escenario", "cuenta_id"]).sum())
    regla("V02", "cuentas", "Sin nulos en columnas obligatorias", cuentas[req_c].isna().sum().sum())
    regla("V03", "cuentas", "es_fraude ∈ {0, 1}", (~cuentas.es_fraude.isin([0, 1])).sum())
    regla("V04", "cuentas", "saldo_inicial ≥ 0", (cuentas.saldo_inicial < 0).sum())
    regla("V05", "cuentas", "Cuenta no fraudulenta sin paso de fraude", (cuentas.es_fraude.eq(0) & cuentas.paso_fraude.notna()).sum())
    regla("V06", "cuentas", "Sin valores centinela (-1) en paso_fraude", cuentas.paso_fraude.eq(CENTINELA_SIN_PASO).sum())
    regla("V07", "transacciones", "Llave tx_id única", tx.tx_id.duplicated().sum())
    regla("V08", "transacciones", "Sin nulos en columnas obligatorias", tx[req_t].isna().sum().sum())
    regla("V09", "transacciones", "monto > 0", (tx.monto <= 0).sum())
    regla("V10", "transacciones", "monto con máximo 2 decimales", ((tx.monto * 100).round(6) % 1 != 0).sum())
    regla("V11", "transacciones", "paso ≥ 1", (tx.paso < 1).sum())
    regla("V12", "transacciones", "cuenta_origen ≠ cuenta_destino", tx.cuenta_origen.eq(tx.cuenta_destino).sum())
    llaves = set(zip(cuentas.escenario, cuentas.cuenta_id))
    fk = lambda col: sum((e, c) not in llaves for e, c in zip(tx.escenario, tx[col]))
    regla("V13", "transacciones", "cuenta_origen existe en cuentas (FK)", fk("cuenta_origen"))
    regla("V14", "transacciones", "cuenta_destino existe en cuentas (FK)", fk("cuenta_destino"))
    regla("V15", "transacciones", "Sin duplicados exactos (escenario, origen, destino, paso, monto)",
          tx.duplicated(["escenario", "cuenta_origen", "cuenta_destino", "paso", "monto"]).sum())
    regla("V16", "transacciones", "fecha = FECHA_BASE + paso días",
          (pd.to_datetime(tx.fecha) != F_BASE + pd.to_timedelta(tx.paso.astype("int64"), unit="D")).sum())
    for esc, m in metricas.items():
        mc, mt = m["cuentas"], m["transacciones"]
        regla(f"R-{esc}-C", "conciliación", f"{esc}: cuentas Bronce = Plata + cuarentena",
              mc["filas_bronce"] - mc["filas_plata"] - mc["filas_cuarentena"])
        regla(f"R-{esc}-T", "conciliación",
              f"{esc}: transacciones Bronce = Σ n_registros_origen + cuarentena",
              mt["filas_bronce"] - mt["registros_representados"] - mt["filas_cuarentena"])
    return chk


# --------------------------------------------------------------------------- principal
def main():
    DIR_PLATA.mkdir(parents=True, exist_ok=True)
    (DIR_PLATA / "csv").mkdir(exist_ok=True)
    todas = {"cuentas": [], "transacciones": [], "q_cuentas": [], "q_tx": []}
    metricas, observaciones = {}, {}

    for esc in ESCENARIOS:
        print(f"[plata] {esc}")
        cuentas, q_c, met_c = limpiar_cuentas(esc)
        tx, q_t, met_t = limpiar_transacciones(esc, cuentas)
        activas = set(tx.cuenta_origen) | set(tx.cuenta_destino)
        cuentas["tiene_transacciones"] = cuentas.cuenta_id.isin(activas)
        met_c["filas_cuarentena"] = len(q_c)
        met_t["filas_cuarentena"] = len(q_t)
        met_t["registros_representados"] = int(tx.n_registros_origen.sum())
        metricas[esc] = {"cuentas": met_c, "transacciones": met_t}
        observaciones[esc] = observar(esc, cuentas, tx, q_t, met_t)
        for k, v in (("cuentas", cuentas), ("transacciones", tx), ("q_cuentas", q_c), ("q_tx", q_t)):
            todas[k].append(v)
        print(f"  cuentas {met_c['filas_bronce']:,} -> {met_c['filas_plata']:,} | "
              f"tx {met_t['filas_bronce']:,} -> {met_t['filas_plata']:,} "
              f"(cuarentena {len(q_t)}, duplicados colapsados {met_t['T5_duplicados_colapsados']})")

    linaje = lambda df, archivo: df.assign(
        archivo_origen=df.escenario.map(lambda e: f"bronce/{e}/{archivo}"),
        fecha_proceso=FECHA_PROCESO)

    cuentas = linaje(pd.concat(todas["cuentas"], ignore_index=True), "nodes.csv")[[
        "escenario", "cuenta_id", "es_fraude", "saldo_inicial", "paso_fraude", "fecha_fraude",
        "paso_fraude_registrado", "tiene_transacciones", "fila_bronce", "archivo_origen", "fecha_proceso"]]
    tx = pd.concat(todas["transacciones"], ignore_index=True)
    tx.insert(0, "tx_id", np.arange(1, len(tx) + 1, dtype="int64"))
    tx = linaje(tx, "transactions.csv")[[
        "tx_id", "escenario", "cuenta_origen", "cuenta_destino", "monto", "paso", "fecha",
        "n_registros_origen", "fila_bronce", "archivo_origen", "fecha_proceso"]]
    q_c = pd.concat(todas["q_cuentas"], ignore_index=True)
    q_t = pd.concat(todas["q_tx"], ignore_index=True)
    for q in (cuentas, tx):
        q["escenario"] = q.escenario.astype("category")

    chequeos = validar(cuentas, tx, metricas)
    fallidos = [c for c in chequeos if not c["ok"]]

    salidas = {"cuentas": cuentas, "transacciones": tx,
               "cuarentena_cuentas": q_c, "cuarentena_transacciones": q_t}
    for nombre, df in salidas.items():
        df.to_parquet(DIR_PLATA / f"{nombre}.parquet", index=False)
        # Copia CSV liviana para revisión (sin columnas de linaje repetidas por fila)
        df.drop(columns=["archivo_origen", "fecha_proceso"], errors="ignore").to_csv(
            DIR_PLATA / "csv" / f"{nombre}.csv", index=False, encoding="utf-8")

    reporte = {
        "capa": "plata",
        "fecha_proceso_utc": FECHA_PROCESO.isoformat(),
        "supuestos": {"fecha_base": FECHA_BASE, "unidad_paso": "1 día (convención AMLSim conf.json)",
                      "centinela_sin_paso": CENTINELA_SIN_PASO},
        "tablas": {n: {"filas": len(d), "columnas": {c: str(t) for c, t in d.dtypes.items()}}
                   for n, d in salidas.items()},
        "metricas_por_regla": metricas,
        "observaciones": observaciones,
        "validaciones": chequeos,
        "resultado": "OK" if not fallidos else "FALLÓ",
    }
    (DIR_PLATA / "_reporte_calidad_plata.json").write_text(
        json.dumps(reporte, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"[plata] validaciones: {len(chequeos) - len(fallidos)}/{len(chequeos)} OK")
    for c in fallidos:
        print(f"  FALLÓ {c['id']} {c['descripcion']}: {c['violaciones']} violaciones")
    sys.exit(1 if fallidos else 0)


if __name__ == "__main__":
    main()
