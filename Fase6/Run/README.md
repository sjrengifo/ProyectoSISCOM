# FASE 6 — Analítica agrícola y predicción

Modelos de aprendizaje automático que predicen variables agroclimáticas y anticipan alertas críticas con 48 h de antelación, usando el dataset histórico de las Fases 1-4 (52.600 registros, 18 años, 8 ubicaciones en Colombia).

---

## Archivos entregados

| Archivo | Propósito |
|---|---|
| `Fase6_Analitica_Prediccion.ipynb` | Notebook con todo el flujo — variables, entrenamiento, evaluación, recomendaciones |
| `dataset_agroclimatico_colombia.csv` | Dataset histórico de Fase 1 corregido (insumo del entrenamiento) |
| `modelos_agroclimaticos_fase6.joblib` | Modelos entrenados serializados (4 RF multi-output + 1 Gradient Boosting) |
| `CONFIGURACION_FASE6.md` | Guía de instalación y ejecución |
| `README.md` | Este archivo |

---

## Inicio rápido (3 pasos)

### Paso 1 — Instalar dependencias

```bash
pip install pandas numpy scikit-learn matplotlib seaborn joblib jupyter
```

### Paso 2 — Lanzar el notebook

```bash
cd /ruta/a/fase6
jupyter notebook Fase6_Analitica_Prediccion.ipynb
# Cell → Run All  (~2-3 minutos de entrenamiento)
```

### Paso 3 — Cargar modelos en producción

```python
import joblib
bundle = joblib.load('modelos_agroclimaticos_fase6.joblib')

# Predecir T_min, T_max, VPD, Precipitación a 1/2/3 días
pred_tmin = bundle['modelos_regresion']['temp_aire_min_C'].predict(X_nuevo)  # shape (n, 3)
prob_alerta = bundle['modelo_clasificacion'].predict_proba(X_nuevo)[:, 1]
```

---

## Estrategia de los dos modelos

### Modelo A — Regresión multi-horizonte

**Un Random Forest multi-output por variable** que predice los próximos 1, 2 y 3 días simultáneamente. Más eficiente que entrenar 12 modelos separados (uno por variable × horizonte) sin pérdida de precisión.

**Variables predichas:**

| Variable | Por qué importa |
|---|---|
| `temp_aire_min_C` | T_min < 18°C arruina cosecha de arroz en floración (esterilidad) |
| `temp_aire_max_C` | T_max > 35°C dispara estrés térmico |
| `vpd_kPa` | VPD > 1.6 kPa = estrés hídrico atmosférico — programar riego |
| `precipitacion_mm` | Decisión de aplicar fertilizante / fitosanitarios |

### Modelo B — Clasificación binaria de alertas a 48 h

**Gradient Boosting** que predice si en las próximas 48 h se violará algún umbral CRITICAL definido en Fase 5 (caña: T>38°C, VPD>2 kPa, lluvia>50 mm; arroz: T>35°C, T_min<18°C, VPD>2 kPa, lluvia>80 mm).

**Caso de uso:** anticipación al sistema reactivo de Fase 5. Permite **acción preventiva** (inundar arroz preventivamente, llenar bombas de riego, aplicar fungicida).

---

## Resultados reales obtenidos (test 2023-2024)

### Modelo A — Métricas de regresión

| Variable | MAE 24h | RMSE 24h | R² | Mejora vs persistencia |
|---|---|---|---|---|
| T_min | **0.91 °C** | 1.13 °C | 0.82 | **+28%** |
| T_max | **0.93 °C** | 1.16 °C | 0.81 | **+28%** |
| VPD | **0.141 kPa** | 0.179 kPa | 0.78 | **+28%** |
| Precipitación | 2.30 mm | 3.59 mm | 0.08 | +17% |

**Interpretación:**
- MAE de T_min ≈ 0.91°C significa que el modelo predice la temperatura mínima de mañana con error típico de 1°C — suficiente para decidir si inundar arroz preventivamente cuando se anticipa T_min<19°C.
- VPD MAE = 0.14 kPa es excelente para un rango operativo de 0-3 kPa.
- Precipitación tiene R² bajo (limitación inherente: predecir lluvia puntual sin información sinóptica regional es difícil), pero aun así supera al baseline ingenuo.

### Modelo B — Métricas de clasificación

| Métrica | Test |
|---|---|
| Accuracy | 0.93 |
| Precision (alerta) | 0.71 |
| Recall (alerta) | 0.67 |
| F1 (alerta) | 0.69 |

**Interpretación:**
- De cada 100 alertas que el modelo predice, **71 son reales** (precisión razonable, baja tasa de falsos positivos).
- De cada 100 alertas reales que ocurrieron, el modelo **anticipa 67 con 48h de antelación** (recall útil).
- F1=0.69 es excelente considerando que solo el 11% de los días tienen alerta crítica (clase muy desbalanceada).

### Top 5 features más importantes para T_min

1. `temp_aire_avg_C_ma7` — media móvil 7 días de T_avg (0.89)
2. `cos_anio` — estacionalidad anual (0.08)
3. `altitud_m` — altitud de la parcela (0.01)
4. `loc_Caicedonia_VAC` — efecto zona (0.003)
5. `sin_anio` — estacionalidad anual (0.002)

**Lectura agronómica:** lo esperado y correcto — la tendencia semanal reciente de temperatura es de lejos el mejor predictor del clima de mañana. La estacionalidad anual aporta corrección secundaria.

---

## Recomendaciones para producción

### En tu máquina local con más RAM

Los hiperparámetros actuales (`n_estimators=30, max_depth=10`) están conservadores para correr rápido. En tu Mac con más recursos puedes mejorar las métricas ~5-10%:

```python
modelo = RandomForestRegressor(
    n_estimators=100,    # de 30 a 100 — entrenar ~3x más lento pero MAE -5%
    max_depth=15,        # de 10 a 15 — capturar interacciones más complejas
    min_samples_leaf=10, # de 15 a 10
    n_jobs=-1            # usar todos los cores
)
```

### Re-entrenamiento mensual programado

El clima cambia, los modelos se desactualizan. Programar un cron mensual:

```bash
# Crontab: 1ro de cada mes a las 3 AM
0 3 1 * * cd /ruta/fase6 && jupyter nbconvert --execute Fase6_Analitica_Prediccion.ipynb
```

### Monitor de drift

Comparar el MAE móvil de los últimos 7 días con el MAE de test (0.91°C para T_min). Si aumenta >20% sostenidamente, re-entrenar urgente.

---

## Cumplimiento de los entregables del PDF

| # | Entregable | Estado |
|---|---|---|
| 1 | **Variable selection** | ✅ §2: features estacionales + lags + indicadores Fase 4 (51 features), justificadas agronómicamente |
| 2 | **Model training** | ✅ §4 (4 RF multi-output) + §5 (1 GBM) con split temporal estricto train 2007-2021 / val 2022 / test 2023-2024 |
| 3 | **Prediction results** | ✅ §4 (tabla MAE/RMSE/R²) + §5 (matriz confusión) + §6 (por zona) + §7 (recomendación accionable por parcela) |

---

## Limitaciones reconocidas

- **Sin labels de rendimiento (TCH/t·ha⁻¹)**: la pregunta más valiosa (¿cuánto va a producir?) queda fuera del alcance hasta tener historial de cosechas.
- **R² de precipitación bajo (0.08)**: limitación inherente con datos puntuales sin información sinóptica regional. Mejorable con datos de pronóstico numérico (ECMWF/GFS).
- **Horizonte máximo 3 días**: extender a 7-14 días requeriría modelos LSTM/Transformers y/o datos satelitales adicionales.
- **Variedad de cultivo no diferenciada**: el modelo no distingue entre FEDEARROZ 174 y FEDEARROZ 68 — diferentes umbrales podrían afinarse con más datos.

---

## Próximos pasos

**Fase 7 — Dashboard Grafana:**

Visualizar las predicciones de este modelo como:

1. **Mapa de calor parcela × variable × horizonte**: vista panorámica de la semana entera.
2. **Indicador semáforo por parcela**: verde / amarillo / rojo según `P(alerta crítica 48h)`.
3. **Comparativa real vs predicho continua**: auditoría del modelo en producción.
4. **Re-entrenamiento programado** con notificación cuando termine.
