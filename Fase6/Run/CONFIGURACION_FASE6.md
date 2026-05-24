# Configuración de la Fase 6 — Analítica predictiva

Esta fase **no requiere infraestructura nueva** — usa el dataset histórico de la Fase 1 y produce modelos serializados con `joblib` para usar en cualquier proceso Python posterior.

---

## 1. Prerrequisitos

- Python 3.10+ (recomendado: 3.11 o 3.12)
- ~4 GB de RAM (los modelos quedan en ~8 MB en disco, pero el entrenamiento usa hasta 1-2 GB)
- Dataset histórico de Fase 1 (`dataset_agroclimatico_colombia.csv`, 15 MB)

## 2. Instalación de dependencias

```bash
pip install pandas numpy scikit-learn matplotlib seaborn joblib jupyter
```

Verificación:

```bash
python3 -c "
import pandas, numpy, sklearn, matplotlib, seaborn, joblib
print(f'pandas:  {pandas.__version__}')
print(f'numpy:   {numpy.__version__}')
print(f'sklearn: {sklearn.__version__}')
"
```

## 3. Estructura de archivos esperada

```
fase6/
├── Fase6_Analitica_Prediccion.ipynb     # Notebook principal
├── dataset_agroclimatico_colombia.csv    # Dataset de Fase 1
├── modelos_agroclimaticos_fase6.joblib   # Modelos serializados (se genera al ejecutar)
├── README.md
└── CONFIGURACION_FASE6.md
```

## 4. Ejecución del notebook

### Opción A — Jupyter clásico

```bash
cd /ruta/a/fase6
jupyter notebook Fase6_Analitica_Prediccion.ipynb
```

En el navegador: **Cell → Run All**. Tarda ~2-3 minutos.

### Opción B — Línea de comandos (para producción/cron)

```bash
jupyter nbconvert --execute --to notebook --output Fase6_ejecutado.ipynb \
                  Fase6_Analitica_Prediccion.ipynb
```

### Opción C — Como script Python (sin notebook)

Si solo quieres entrenar y persistir sin la documentación interactiva:

```bash
# Extraer solo el código (sin markdown)
jupyter nbconvert --to script Fase6_Analitica_Prediccion.ipynb
python3 Fase6_Analitica_Prediccion.py
```

## 5. Carga de modelos para predicción

Una vez entrenado, el archivo `modelos_agroclimaticos_fase6.joblib` contiene todo lo necesario:

```python
import joblib
import pandas as pd

# Cargar el bundle
bundle = joblib.load('modelos_agroclimaticos_fase6.joblib')

print(f'Modelos disponibles: {list(bundle["modelos_regresion"].keys())}')
# ['temp_aire_min_C', 'temp_aire_max_C', 'vpd_kPa', 'precipitacion_mm']

print(f'Features esperados: {len(bundle["features"])}')
# 51
print(f'Targets: {bundle["targets"]}')
# ['target_temp_aire_min_C_h1', ... 'target_precipitacion_mm_h3']

# X_nuevo debe tener las mismas columnas que bundle['features']
# Cada modelo de regresión devuelve un array (n_filas, 3) con las predicciones
# a 1, 2 y 3 días
pred_tmin = bundle['modelos_regresion']['temp_aire_min_C'].predict(X_nuevo)
print(pred_tmin.shape)  # (n, 3)

# Modelo de clasificación devuelve probabilidad de alerta crítica a 48h
prob_alerta = bundle['modelo_clasificacion'].predict_proba(X_nuevo)[:, 1]
```

## 6. Integración con la Fase 5 (alertas)

El servicio `servicio_alertas.py` de la Fase 5 dispara alertas **reactivas** (cuando la condición ya ocurrió). Para integrar las predicciones a 48 h y obtener alertas **predictivas**:

```python
# pseudo-código del servicio extendido
import joblib
import influxdb_client

bundle = joblib.load('modelos_agroclimaticos_fase6.joblib')

def ciclo_prediccion(parcelas_recientes):
    """Ejecutar cada hora. Anticipa alertas con 48 h de antelación."""
    features = construir_features(parcelas_recientes)  # mismas que entrenamiento
    X = features[bundle['features']].values
    
    # Probabilidad de alerta crítica a 48 h por parcela
    proba = bundle['modelo_clasificacion'].predict_proba(X)[:, 1]
    
    for i, p in enumerate(proba):
        if p > 0.6:  # umbral para alerta predictiva
            publicar_alerta_mqtt(
                topico=f'agricultura/alertas_predictivas/...',
                payload={'probabilidad': p, 'horizonte': '48h', ...}
            )
```

## 7. Re-entrenamiento programado

Los modelos se desactualizan con el tiempo (drift climático). Recomendado: re-entrenar cada mes con datos más recientes.

### macOS / Linux — usando crontab

```bash
crontab -e
# Añadir:
0 3 1 * * cd /Users/tu_usuario/fase6 && /usr/bin/env python3 -m jupyter nbconvert --execute Fase6_Analitica_Prediccion.ipynb --to notebook --output ejecutados/Fase6_$(date +\%Y\%m).ipynb 2>&1 | logger -t fase6_reentrenamiento
```

### macOS — usando launchd (más nativo)

Crear `~/Library/LaunchAgents/com.icesi.agro.fase6.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>Label</key><string>com.icesi.agro.fase6</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>-m</string><string>jupyter</string>
        <string>nbconvert</string><string>--execute</string>
        <string>/Users/tu_usuario/fase6/Fase6_Analitica_Prediccion.ipynb</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Day</key>     <integer>1</integer>
        <key>Hour</key>    <integer>3</integer>
        <key>Minute</key>  <integer>0</integer>
    </dict>
</dict>
</plist>
```

Activar:

```bash
launchctl load ~/Library/LaunchAgents/com.icesi.agro.fase6.plist
```

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `FileNotFoundError: dataset_agroclimatico_colombia.csv` | Dataset no en directorio actual | Copiar desde `fase1/` o usar `cd` al directorio correcto |
| `MemoryError` durante entrenamiento | RAM insuficiente | Reducir `n_estimators` a 20, `max_depth` a 8 |
| Entrenamiento muy lento (>10 min por modelo) | CPU/RAM limitada | Usar `n_jobs=2` o `n_jobs=1` en lugar de `-1` |
| `joblib.load` falla con `ModuleNotFoundError` | Versiones distintas de sklearn | Recrear con misma versión: `pip install scikit-learn==1.x.x` |
| Métricas mucho peores que las reportadas | Versión del dataset distinta | Verificar que es el dataset de Fase 1 corregido (Palmira ≈ 24°C, no ≈ 16°C) |
| Resultados no determinísticos entre corridas | Falta `random_state=42` en algún modelo | Verificar que TODOS los estimadores tengan `random_state=42` |

## 9. Optimización para producción

### Si tu Mac tiene 16+ GB RAM

Mejora las métricas ~5-10%:

```python
RandomForestRegressor(
    n_estimators=200, max_depth=20, min_samples_leaf=5, n_jobs=-1, random_state=42
)
```

### Si quieres velocidad de inferencia máxima

Convierte a un modelo más ligero usando `XGBoost` o `LightGBM` (requieren instalación adicional):

```bash
pip install lightgbm
```

```python
from lightgbm import LGBMRegressor
# 5-10× más rápido que sklearn RandomForest con métricas similares
```

## 10. Próximo paso

**Fase 7 — Dashboard Grafana** consumirá los modelos persistidos para mostrar:
- Predicciones a 1/2/3 días por parcela (mapa de calor).
- Probabilidad de alerta crítica con semáforo.
- Comparativa real vs predicho para monitor continuo del drift.
