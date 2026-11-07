"""Prueba de las reglas de Plata con datos sucios sembrados a propósito.

El dataset oficial de AMLSim viene casi limpio (sin nulos ni tipos inválidos), así que
esta prueba demuestra que cada regla detecta y aísla el error que le corresponde.

Uso:  python tests/prueba_reglas_plata.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import plata_limpieza as pl  # noqa: E402

CUENTAS = """nodeid,isFraud,init_balance,fraudStep
0,0,100.5,-1
1,1,200,5
2,0,abc,-1
3,,150,-1
4,2,150,-1
5,0,-10,-1
1,0,300,-1
6,0,120,7
7,1,130,-1
"""
# fila: comentario
TRANSACCIONES = """sourceNodeId,targetNodeId,value,time
0,1,50.5,1
0,1,50.5,1
0,1,50.50,1
1,0,x,2
1,0,,2
1,0,-5,2
1,0,10,0
0,99,10,3
2,0,10,3
6,6,10,3
0,1,10.5,1.5
6,7,20,4
"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        esc = "PRUEBA"
        (Path(tmp) / esc).mkdir()
        (Path(tmp) / esc / "nodes.csv").write_text(CUENTAS, encoding="utf-8")
        (Path(tmp) / esc / "transactions.csv").write_text(TRANSACCIONES, encoding="utf-8")
        pl.DIR_BRONCE = Path(tmp)

        cuentas, q_c, m_c = pl.limpiar_cuentas(esc)
        tx, q_t, m_t = pl.limpiar_transacciones(esc, cuentas)

    esperado_c = {"C1_tipado_nulos": 2,            # 'abc' en saldo, es_fraude vacío
                  "C2_dominio": 2,                 # es_fraude=2, saldo negativo
                  "C3_llave_duplicada": 1,         # cuenta 1 repetida
                  "C5_paso_en_no_fraude_corregido": 1,  # cuenta 6 no fraude con paso 7
                  "filas_plata": 4}
    esperado_t = {"T1_tipado_nulos": 3,            # 'x', vacío, paso 1.5
                  "T2_dominio": 2,                 # monto -5, paso 0
                  "T3_integridad_referencial": 2,  # destino 99, origen 2 (en cuarentena)
                  "T4_autotransferencia": 1,       # 6 -> 6
                  "T5_duplicados_colapsados": 2,   # 3 registros 0->1 de 50.50 => 1
                  "filas_plata": 2}
    errores = []
    for nombre, esp, real in (("cuentas", esperado_c, m_c), ("transacciones", esperado_t, m_t)):
        for k, v in esp.items():
            estado = "OK " if real[k] == v else "ERR"
            if real[k] != v:
                errores.append(k)
            print(f"  [{estado}] {nombre:13s} {k:32s} esperado={v} obtenido={real[k]}")

    assert sorted(cuentas.cuenta_id) == [0, 1, 6, 7]
    assert cuentas.set_index("cuenta_id").loc[6, "paso_fraude"] is __import__("pandas").NA
    assert not cuentas.set_index("cuenta_id").loc[7, "paso_fraude_registrado"]
    assert tx.n_registros_origen.max() == 3
    assert len(q_t) + tx.n_registros_origen.sum() == m_t["filas_bronce"], "conciliación"
    if errores:
        sys.exit(f"Fallaron: {errores}")
    print(f"Todas las reglas se comportan como se espera "
          f"({len(q_c)} cuentas y {len(q_t)} transacciones en cuarentena).")


if __name__ == "__main__":
    main()
