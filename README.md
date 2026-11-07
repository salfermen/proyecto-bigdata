# Avance: etapa Plata con AMLSim (SARLAFT)

Pipeline medallón (Bronce → Plata) sobre el dataset **AMLSim (IBM & MIT)**, elegido en la actividad
*Búsqueda y selección de fuentes de datos* para entrenar una red neuronal densa que asigne un puntaje
de riesgo por cuenta.

El informe del avance está en [reportes/Avance_Etapa_Plata_AMLSim.docx](reportes/Avance_Etapa_Plata_AMLSim.docx).
Contiene las secciones 1 a 4 de la actividad original y agrega las secciones 5 a 10.

## Estructura

```
src/
  config.py               rutas, escenarios y convenciones (fecha base, centinela)
  bronce_ingesta.py       descarga y extrae los datos oficiales y genera el manifiesto de linaje
  plata_limpieza.py       aplica las reglas de limpieza, la cuarentena y el contrato de validación
  figuras_plata.py        genera las figuras exploratorias del informe
tests/
  prueba_reglas_plata.py  siembra errores a propósito y comprueba que cada regla los detecta
data/
  bronce/                 datos crudos sin modificar + _manifiesto_bronce.json (URL, SHA-256, filas)
  plata/                  cuentas, transacciones y cuarentena (Parquet) + _reporte_calidad_plata.json
  plata/csv/              copias CSV para revisión (sin columnas de linaje)
reportes/
  Avance_Etapa_Plata_AMLSim.docx
  figuras/
```

## Cómo ejecutarlo

```bash
pip install -r requirements.txt
```

```bash
python src/bronce_ingesta.py
```

```bash
python src/plata_limpieza.py
```

```bash
python tests/prueba_reglas_plata.py
```

```bash
python src/figuras_plata.py
```

`plata_limpieza.py` termina con código 1 si falla alguna de las 22 validaciones.

## Fuente

Se usan los datasets de ejemplo oficiales de `IBM/AMLSim` (carpeta `sample/`, rama `master`). Tienen
20.000 cuentas y tres escenarios: `20K_fanin200cycle200` (principal), `20K_fanin200` y `20K_cycle200`.

## Resultado de la capa Plata

| Escenario | Tx Bronce | Autotransferencias (cuarentena) | Duplicados colapsados | Tx Plata |
|---|---:|---:|---:|---:|
| 20K_fanin200cycle200 | 120.558 | 15 | 1.684 | 118.859 |
| 20K_fanin200 | 118.250 | 14 | 254 | 117.982 |
| 20K_cycle200 | 117.805 | 14 | 1.420 | 116.371 |
| **Total** | **356.613** | **43** | **3.358** | **353.212** |

Las 60.000 cuentas pasan completas. El valor centinela `fraudStep = -1` se convierte en nulo, y la conciliación
Bronce = Plata + cuarentena se cumple en todas las tablas.

### Reglas

| Código | Regla | Acción |
|---|---|---|
| C1 / T1 | Tipado y nulos | Cuarentena |
| C2 / T2 | Dominio (etiqueta 0/1, saldo ≥ 0, monto > 0, paso ≥ 1) | Cuarentena |
| C3 | Llave `cuenta_id` única por escenario | Cuarentena del repetido |
| C4 | Centinela −1 en `paso_fraude` | Nulo + `paso_fraude_registrado` |
| C5 | Cuenta no fraudulenta con paso de fraude | Corregir a nulo |
| T3 | Integridad referencial origen/destino | Cuarentena |
| T4 | Autotransferencia | Cuarentena |
| T5 | Duplicado exacto (origen, destino, paso, monto) | Colapsar y guardar `n_registros_origen` |

### Supuestos

- `fecha = 2017-01-01 + paso` (convención `base_date` de AMLSim; 1 paso = 1 día).
- Los duplicados exactos se colapsan porque el dataset no trae un identificador de transacción. El conteo se
  conserva, así que la decisión es reversible.

## Puntos a tener en cuenta para la etapa Oro

- **Posible leakage:** toda transacción con monto < 100 es entre cuentas fraudulentas, porque así lo genera el
  simulador. Conviene comparar el desempeño con y sin variables de monto pequeño.
- **Desbalance:** entre 4,7 % y 9 % de cuentas fraudulentas. Se recomienda evaluar con PR-AUC y recall@k.
- **La etiqueta es por cuenta:** hay que agregar las transacciones por cuenta antes de entrenar.
