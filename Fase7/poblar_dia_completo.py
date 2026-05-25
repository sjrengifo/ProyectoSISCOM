#!/usr/bin/env python3
"""
poblar_dia_completo.py
======================
Puebla InfluxDB con datos densos (cada --intervalo minutos) para un día completo,
derivados del dataset histórico del CSV. Genera:
  - sensor_data       → bucket agro_iot_data
  - indicadores       → bucket agro_iot_indicadores
  - alertas           → bucket agro_iot_indicadores (evaluando umbrales del YAML)
  - prediccion_modelo_B → bucket agro_iot_indicadores (usando modelo joblib)

Uso:
    python3 Fase7/poblar_dia_completo.py [--fecha YYYY-MM-DD] [--intervalo 15] [--dry-run]
"""

import argparse
import math
import os
import random
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Credenciales (sobreescribibles con variables de entorno) ───
INFLUX_URL   = os.environ.get("INFLUX_URL",        "http://localhost:8086")
INFLUX_ORG   = os.environ.get("INFLUX_ORG",        "agricultura")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN",       "z5MJcpefAqdYup07U7RIo8bzKjj4gMdcKjxLFAgf-lOIFJk7PXfWdggz-vs3k97lVuF164JEErRM7JqVlzp-Hw==")
BUCKET_RAW   = os.environ.get("INFLUX_BUCKET_RAW", "agro_iot_data")
BUCKET_IND   = os.environ.get("INFLUX_BUCKET_IND", "agro_iot_indicadores")

# ── Topología de parcelas ─────────────────────────────────────
TOPOLOGIA = {
    "parcela_1": {
        "cultivo": "caña", "ubicacion": "Palmira_VAC",
        "departamento": "Valle del Cauca", "T_base": 10,
        "lat": 3.51, "lon": -76.31, "altitud": 1001,
    },
    "parcela_2": {
        "cultivo": "caña", "ubicacion": "Candelaria_VAC",
        "departamento": "Valle del Cauca", "T_base": 10,
        "lat": 3.41, "lon": -76.34, "altitud": 980,
    },
    "parcela_3": {
        "cultivo": "arroz", "ubicacion": "Espinal_TOL",
        "departamento": "Tolima", "T_base": 15,
        "lat": 4.15, "lon": -74.88, "altitud": 323,
    },
    "parcela_4": {
        "cultivo": "arroz", "ubicacion": "Yopal_CAS",
        "departamento": "Casanare", "T_base": 15,
        "lat": 5.34, "lon": -72.40, "altitud": 355,
    },
}

UNIDADES = {
    "temperatura_aire":  "°C",   "temperatura_suelo": "°C",
    "humedad_relativa":  "%",    "humedad_suelo":     "%",
    "precipitacion":     "mm",   "radiacion_solar":   "MJ/m²",
    "velocidad_viento":  "m/s",  "ph_suelo":          "pH",
}

# ── Funciones de curva diurna ─────────────────────────────────

def temperatura_diurna(T_avg, T_max, T_min, hora_utc, offset_h=-5):
    """Curva sinusoidal: mínimo a 6 AM local, máximo a 14 PM local."""
    hora_local = (hora_utc + offset_h) % 24
    A = (T_max - T_min) / 2.0
    # sin pasa por 0 en t=0 (mínimo a ~6h si desfasamos a las 6am)
    T = T_avg + A * math.sin(2 * math.pi * (hora_local - 6.0) / 24.0)
    return round(T + random.gauss(0, 0.3), 2)


def humedad_diurna(HR_avg, T, T_avg):
    """HR inversamente correlada con T°."""
    delta = (T - T_avg) * 1.5
    HR = HR_avg - delta + random.gauss(0, 1.5)
    return round(min(98, max(35, HR)), 1)


def radiacion_diurna(R_total, hora_utc, offset_h=-5):
    """Gaussiana centrada en mediodía local (12:30)."""
    hora_local = (hora_utc + offset_h) % 24
    if hora_local < 6 or hora_local >= 19:
        return 0.0
    sigma = 3.0
    centro = 12.5
    factor = math.exp(-0.5 * ((hora_local - centro) / sigma) ** 2)
    # Normalizar: integral gaussiana 6→19 ≈ factor total
    R = R_total * factor * (13 / (sigma * math.sqrt(2 * math.pi) * 0.997))
    return round(max(0, R + random.gauss(0, R * 0.05)), 3)


def precipitacion_diurna(precip_total, hora_utc, offset_h=-5):
    """Lluvia concentrada en tarde (14-18h local) si hay precipitación diaria."""
    if precip_total <= 0:
        return 0.0
    hora_local = (hora_utc + offset_h) % 24
    if 14 <= hora_local < 18:
        if random.random() < 0.3:
            return round(random.expovariate(1.0 / (precip_total / 4.0)), 2)
    return 0.0


# ── Cálculo de indicadores ────────────────────────────────────

def calc_vpd(T, HR):
    es = 0.6108 * math.exp(17.27 * T / (T + 237.3))
    return round(max(0, es * (1.0 - HR / 100.0)), 4)


def calc_punto_rocio(T, HR):
    HR = max(1, HR)
    ln_hr = math.log(HR / 100.0)
    return round(243.04 * (ln_hr + 17.625 * T / (243.04 + T)) /
                 (17.625 - ln_hr - 17.625 * T / (243.04 + T)), 2)


def calc_indice_calor(T, HR):
    """Fórmula Steadman / NWS (en °C)."""
    if T < 27:
        return round(T, 2)
    c = [-8.78469475556, 1.61139411, 2.33854883889, -0.14611605,
         -0.012308094, -0.0164248277778, 0.002211732, 0.00072546,
         -0.000003582]
    HI = (c[0] + c[1]*T + c[2]*HR + c[3]*T*HR + c[4]*T**2 + c[5]*HR**2
          + c[6]*T**2*HR + c[7]*T*HR**2 + c[8]*T**2*HR**2)
    return round(HI, 2)


def calc_gdd(T, T_base):
    return round(max(0.0, T - T_base), 4)


def calc_eto(T_avg, T_max, T_min, R_mj):
    """Hargreaves-Samani simplificado (mm/período)."""
    if T_max <= T_min:
        return 0.0
    eto = 0.0023 * (T_avg + 17.8) * math.sqrt(max(0.1, T_max - T_min)) * R_mj * 0.408
    return round(max(0, eto), 4)


# ── Evaluación de umbrales ────────────────────────────────────

def evaluar_umbrales(cfg, cultivo, indicadores_vals):
    """Devuelve lista de alertas disparadas según umbrales YAML.
    Si una variable dispara múltiples niveles, se toma el más grave (critical > warning > info).
    """
    SEVERIDAD = {"critical": 3, "warning": 2, "info": 1}
    alertas = []
    secciones_cultivo = cfg.get(cultivo, {})
    variables = secciones_cultivo.get("variables", {})
    for var, props in variables.items():
        valor = indicadores_vals.get(var)
        if valor is None:
            continue
        umbrales = props.get("umbrales", [])
        # Evaluar en orden de severidad descendente para tomar la más grave
        umbrales_ord = sorted(umbrales,
                              key=lambda u: SEVERIDAD.get(u.get("nivel", "info"), 0),
                              reverse=True)
        for u in umbrales_ord:
            cond = u.get("condicion", "")
            ref  = u.get("valor", 0)
            disparada = False
            if   cond == ">"  and valor > ref:  disparada = True
            elif cond == "<"  and valor < ref:  disparada = True
            elif cond == ">=" and valor >= ref: disparada = True
            elif cond == "<=" and valor <= ref: disparada = True
            if disparada:
                alertas.append({
                    "nivel":    u["nivel"],
                    "variable": var,
                    "valor":    valor,
                    "unidad":   props.get("unidad", ""),
                    "mensaje":  u.get("mensaje", ""),
                    "accion":   u.get("accion",  ""),
                })
                break  # tomar solo la más grave por variable
    return alertas


# ── Script de inferencia ML ───────────────────────────────────

def generar_predicciones_ml(df_csv, hora_utc, topologia):
    """Usa el modelo joblib para generar predicciones por parcela."""
    try:
        import joblib
        modelo_path = BASE_DIR / "Fase6" / "modelos_agroclimaticos_fase6.joblib"
        if not modelo_path.exists():
            return {}
        bundle = joblib.load(modelo_path)
        FEATURES = bundle["features"]
        preds = {}
        for parcela, info in topologia.items():
            ubic = info["ubicacion"]
            sub = df_csv[df_csv["ubicacion"] == ubic]
            if len(sub) == 0:
                continue
            fila = sub.iloc[len(sub) // 2]  # fila representativa
            X = np.zeros((1, len(FEATURES)))
            # Fase2 CSV ya usa los nombres NASA directos (T2M, RH2M, etc.)
            # sin necesidad de remapeo
            col_map = {}
            for i, feat in enumerate(FEATURES):
                mapped = col_map.get(feat, feat)
                if mapped in fila.index:
                    X[0, i] = float(fila[mapped])
                elif feat in fila.index:
                    X[0, i] = float(fila[feat])
                elif feat.startswith("loc_"):
                    X[0, i] = 1.0 if feat == f"loc_{ubic}" else 0.0
                elif feat == "es_cana":
                    X[0, i] = 1.0 if info["cultivo"] == "caña" else 0.0
            prob = float(bundle["modelo_clasificacion"].predict_proba(X)[0, 1])
            pred_tmin = bundle["modelos_regresion"]["temp_aire_min_C"].predict(X)[0]
            pred_tmax = bundle["modelos_regresion"]["temp_aire_max_C"].predict(X)[0]
            pred_vpd  = bundle["modelos_regresion"]["vpd_kPa"].predict(X)[0]
            preds[parcela] = {
                "prob_alerta_critica_48h": prob,
                "tmin_h1": float(pred_tmin[0]),
                "tmin_h2": float(pred_tmin[1]),
                "tmin_h3": float(pred_tmin[2]),
                "tmax_h1": float(pred_tmax[0]),
                "vpd_h1":  float(pred_vpd[0]),
            }
        return preds
    except Exception as e:
        print(f"  ⚠ ML predictions skipped: {e}")
        return {}


# ── Main ──────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Pobla InfluxDB con un día completo de datos agroclimáticos.")
    ap.add_argument("--fecha",     default=None,
                    help="Fecha a poblar YYYY-MM-DD (default: ayer)")
    ap.add_argument("--intervalo", type=int, default=15,
                    help="Minutos entre lecturas (default: 15)")
    ap.add_argument("--dry-run",   action="store_true",
                    help="Solo muestra conteos, no escribe en InfluxDB")
    args = ap.parse_args()

    # Fecha objetivo (Colombia = UTC-5)
    tz_bogota = timezone(timedelta(hours=-5))
    if args.fecha:
        fecha_local = datetime.strptime(args.fecha, "%Y-%m-%d").replace(tzinfo=tz_bogota)
    else:
        fecha_local = (datetime.now(tz_bogota) - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0)

    # Inicio y fin del día en UTC
    inicio_utc = fecha_local.astimezone(timezone.utc)
    fin_utc    = inicio_utc + timedelta(days=1)

    print("=" * 65)
    print(f"  POBLAR DÍA COMPLETO — {fecha_local.strftime('%Y-%m-%d')} (Colombia)")
    print(f"  UTC: {inicio_utc.isoformat()[:19]} → {fin_utc.isoformat()[:19]}")
    print(f"  Intervalo: {args.intervalo} min  |  4 parcelas  |  8 variables")
    print("=" * 65)

    # ── Cargar CSV ───────────────────────────────────────────
    # Usar el CSV corregido de Fase2 (temperaturas ajustadas a valores reales)
    csv_path = BASE_DIR / "Fase2" / "dataset_agroclimatico_colombia.csv"
    df_csv = pd.read_csv(csv_path, parse_dates=["fecha"])
    df_csv["mes"] = df_csv["fecha"].dt.month
    df_csv["dia"] = df_csv["fecha"].dt.day
    mes_obj = fecha_local.month
    dia_obj = fecha_local.day

    # ── Cargar umbrales ──────────────────────────────────────
    yaml_path = BASE_DIR / "Fase5" / "umbrales_agronomicos.yaml"
    with open(yaml_path) as f:
        cfg_umbrales = yaml.safe_load(f)

    # ── Datos base por parcela (del CSV histórico) ───────────
    datos_base = {}
    for parcela, info in TOPOLOGIA.items():
        ubic = info["ubicacion"]
        # Buscar mismo mes+día en años anteriores
        sub = df_csv[(df_csv["ubicacion"] == ubic) &
                     (df_csv["mes"] == mes_obj) &
                     (df_csv["dia"] == dia_obj)]
        if len(sub) == 0:
            # Fallback: mismo mes, día más cercano
            sub = df_csv[(df_csv["ubicacion"] == ubic) & (df_csv["mes"] == mes_obj)]
        if len(sub) == 0:
            sub = df_csv[df_csv["ubicacion"] == ubic]
        # Eliminar filas con NaN en columnas críticas antes de muestrear
        COLS_REQ = ["T2M", "T2M_MAX", "T2M_MIN", "RH2M", "PRECTOTCORR", "WS2M"]
        sub_ok = sub.dropna(subset=COLS_REQ)
        if len(sub_ok) == 0:
            sub_ok = sub  # si todas tienen NaN en algo, usar cualquiera
        row = sub_ok.sample(1).iloc[0] if len(sub_ok) > 1 else sub_ok.iloc[0]

        def _val(r, col, default):
            v = r.get(col, default)
            return float(v) if pd.notna(v) else float(default)

        datos_base[parcela] = {
            "T_avg":  _val(row, "T2M",               24.0),
            "T_max":  _val(row, "T2M_MAX",            30.0),
            "T_min":  _val(row, "T2M_MIN",            18.0),
            "HR_avg": _val(row, "RH2M",               75.0),
            "precip": _val(row, "PRECTOTCORR",         0.0),
            "rad":    _val(row, "ALLSKY_SFC_SW_DWN",  15.0),
            "viento": _val(row, "WS2M",                2.0),
            "pH":     _val(row, "pH_suelo",            6.2),
            "hs":     _val(row, "humedad_suelo_pct",  38.0),
        }

    print("\nDatos base del CSV para esta fecha:")
    for parcela, d in datos_base.items():
        info = TOPOLOGIA[parcela]
        print(f"  {parcela} ({info['ubicacion']}): "
              f"T={d['T_avg']:.1f}°C ({d['T_min']:.1f}-{d['T_max']:.1f}), "
              f"HR={d['HR_avg']:.0f}%, precip={d['precip']:.1f}mm")

    # ── Generar timestamps ───────────────────────────────────
    delta = timedelta(minutes=args.intervalo)
    timestamps = []
    t = inicio_utc
    while t < fin_utc:
        timestamps.append(t)
        t += delta

    n_ts = len(timestamps)
    n_vars = 8
    n_parcelas = 4
    n_indicadores = 5
    total_sensor = n_ts * n_vars * n_parcelas
    total_ind    = n_ts * n_indicadores * n_parcelas
    print(f"\nTimestamps: {n_ts}  ({n_ts * args.intervalo // 60}h de datos)")
    print(f"  sensor_data  → ~{total_sensor:,} puntos")
    print(f"  indicadores  → ~{total_ind:,} puntos")
    print(f"  alertas      → ~{5 * n_parcelas} eventos estimados (con cooldown 30 min)")
    print(f"  predicciones → ~{24 * n_parcelas} puntos (cada hora)")

    if args.dry_run:
        print("\n[DRY-RUN] No se escriben datos.")
        return

    # ── Conectar InfluxDB ────────────────────────────────────
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS

    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    health = client.health()
    print(f"\n✓ InfluxDB {health.version}  status={health.status}")
    write_api = client.write_api(write_options=SYNCHRONOUS)

    BATCH = 500
    buf_raw = []
    buf_ind = []
    buf_ale = []
    written_raw = written_ind = written_ale = written_ml = 0

    # Cooldown de alertas: {(parcela, variable): ultimo_ts}
    cooldown = {}
    COOLDOWN_MIN = 30

    # Timestamps de predicciones ML: cada hora
    ts_ml = [inicio_utc + timedelta(hours=h) for h in range(24)]
    preds_cache = {}

    def flush(buf, bucket):
        nonlocal written_raw, written_ind, written_ale
        if not buf:
            return
        try:
            write_api.write(bucket=bucket, record=buf)
        except Exception as e:
            print(f"    ⚠ write error ({bucket}): {e}")
        buf.clear()

    print("\nEscribiendo datos...")

    for i, ts in enumerate(timestamps):
        hora_utc = ts.hour + ts.minute / 60.0

        for parcela, info in TOPOLOGIA.items():
            cultivo = info["cultivo"]
            ubic    = info["ubicacion"]
            dept    = info["departamento"]
            T_base  = info["T_base"]
            b       = datos_base[parcela]

            # ── Valores de sensores ──────────────────────────
            T_aire = temperatura_diurna(b["T_avg"], b["T_max"], b["T_min"], hora_utc)
            T_suelo = round(T_aire - 1.2 + random.gauss(0, 0.4), 2)
            HR      = humedad_diurna(b["HR_avg"], T_aire, b["T_avg"])
            rad_inst = radiacion_diurna(b["rad"], hora_utc)
            precip_inst = precipitacion_diurna(b["precip"], hora_utc)
            viento  = round(max(0.1, b["viento"] + random.gauss(0, 0.3)), 2)
            hs      = round(min(80, max(20, b["hs"] + random.gauss(0, 0.8))), 1)
            ph      = round(min(8.0, max(4.5, b["pH"] + random.gauss(0, 0.05))), 2)

            sensor_vals = {
                "temperatura_aire":  T_aire,
                "temperatura_suelo": T_suelo,
                "humedad_relativa":  HR,
                "humedad_suelo":     hs,
                "precipitacion":     precip_inst,
                "radiacion_solar":   rad_inst,
                "velocidad_viento":  viento,
                "ph_suelo":          ph,
            }

            for var, val in sensor_vals.items():
                p = (Point("sensor_data")
                     .tag("parcela",     parcela)
                     .tag("cultivo",     cultivo)
                     .tag("ubicacion",   ubic)
                     .tag("departamento", dept)
                     .tag("variable",    var)
                     .tag("unidad",      UNIDADES[var])
                     .tag("sensor_id",   f"{parcela}_{var}")
                     .field(var, float(val))
                     .time(ts, WritePrecision.NS))
                buf_raw.append(p)
                written_raw += 1

            # ── Indicadores calculados ───────────────────────
            vpd          = calc_vpd(T_aire, HR)
            punto_rocio  = calc_punto_rocio(T_aire, HR)
            indice_calor = calc_indice_calor(T_aire, HR)
            gdd_inst     = calc_gdd(T_aire, T_base)
            eto_inst     = calc_eto(T_aire, b["T_max"], b["T_min"], rad_inst)

            indicadores_vals = {
                "vpd":           vpd,
                "punto_rocio":   punto_rocio,
                "indice_calor":  indice_calor,
                "gdd_instantaneo": gdd_inst,
                "eto_hargreaves":  eto_inst,
            }
            unidades_ind = {
                "vpd": "kPa", "punto_rocio": "°C", "indice_calor": "°C",
                "gdd_instantaneo": "°C·día", "eto_hargreaves": "mm/día",
            }

            for ind, val in indicadores_vals.items():
                p = (Point("indicadores")
                     .tag("parcela",     parcela)
                     .tag("cultivo",     cultivo)
                     .tag("ubicacion",   ubic)
                     .tag("departamento", dept)
                     .tag("indicador",   ind)
                     .tag("unidad",      unidades_ind[ind])
                     .field(ind, float(val))
                     .time(ts, WritePrecision.NS))
                buf_ind.append(p)
                written_ind += 1

            # ── Alertas (con cooldown) ───────────────────────
            # Mapear indicadores calculados + variables de sensor para evaluación
            eval_vals = dict(indicadores_vals)
            eval_vals["temperatura_aire"]     = T_aire
            eval_vals["temperatura_aire_min"] = b["T_min"]  # mínimo del día
            eval_vals["humedad_relativa"]      = HR
            eval_vals["precipitacion"]         = b["precip"]  # total diario
            eval_vals["radiacion_solar"]       = b["rad"]
            eval_vals["eto_hargreaves"]        = eto_inst

            alertas = evaluar_umbrales(cfg_umbrales, cultivo, eval_vals)
            for alerta in alertas:
                clave = (parcela, alerta["variable"])
                ultimo = cooldown.get(clave)
                if ultimo is None or (ts - ultimo).total_seconds() >= COOLDOWN_MIN * 60:
                    cooldown[clave] = ts
                    p = (Point("alertas")
                         .tag("nivel",     alerta["nivel"])
                         .tag("parcela",   parcela)
                         .tag("cultivo",   cultivo)
                         .tag("ubicacion", ubic)
                         .field("variable", alerta["variable"])
                         .field("valor",    float(alerta["valor"]))
                         .field("unidad",   alerta["unidad"])
                         .field("mensaje",  alerta["mensaje"])
                         .field("accion",   alerta["accion"])
                         .time(ts, WritePrecision.NS))
                    buf_ale.append(p)
                    written_ale += 1

        # ── Flush sensor_data ────────────────────────────────
        if len(buf_raw) >= BATCH:
            flush(buf_raw, BUCKET_RAW)
        if len(buf_ind) >= BATCH:
            flush(buf_ind, BUCKET_IND)
        if len(buf_ale) >= 50:
            flush(buf_ale, BUCKET_IND)

        # Progreso
        if (i + 1) % 20 == 0 or i == n_ts - 1:
            pct = (i + 1) / n_ts * 100
            print(f"  {pct:5.1f}%  t={ts.strftime('%H:%M UTC')}  "
                  f"raw={written_raw}  ind={written_ind}  ale={written_ale}", end="\r")

    flush(buf_raw, BUCKET_RAW)
    flush(buf_ind, BUCKET_IND)
    flush(buf_ale, BUCKET_IND)
    print()

    # ── Predicciones ML (cada hora) ──────────────────────────
    print("\nGenerando predicciones ML (cada hora)...")
    preds_cache = generar_predicciones_ml(df_csv, 12, TOPOLOGIA)
    if preds_cache:
        buf_ml = []
        for ts_ml_t in ts_ml:
            for parcela, info in TOPOLOGIA.items():
                pred = preds_cache.get(parcela)
                if not pred:
                    continue
                # Añadir variación realista a la probabilidad
                prob = max(0.0, min(1.0, pred["prob_alerta_critica_48h"]
                                   + random.gauss(0, 0.02)))
                p = (Point("prediccion_modelo_B")
                     .tag("parcela",   parcela)
                     .tag("cultivo",   info["cultivo"])
                     .tag("ubicacion", info["ubicacion"])
                     .field("prob_alerta_critica_48h", float(prob))
                     .field("tmin_h1", float(pred["tmin_h1"] + random.gauss(0, 0.1)))
                     .field("tmin_h2", float(pred["tmin_h2"] + random.gauss(0, 0.1)))
                     .field("tmin_h3", float(pred["tmin_h3"] + random.gauss(0, 0.1)))
                     .field("tmax_h1", float(pred["tmax_h1"] + random.gauss(0, 0.1)))
                     .field("vpd_h1",  float(pred["vpd_h1"]  + random.gauss(0, 0.01)))
                     .time(ts_ml_t, WritePrecision.NS))
                buf_ml.append(p)
                written_ml += 1
        write_api.write(bucket=BUCKET_IND, record=buf_ml)
        print(f"  ✓ {written_ml} predicciones ML escritas ({len(ts_ml)} horas × 4 parcelas)")
    else:
        print("  ⚠ Modelo ML no disponible, predicciones omitidas")

    print()
    print("=" * 65)
    print("  RESUMEN DE ESCRITURA")
    print(f"  sensor_data      : {written_raw:,} registros")
    print(f"  indicadores      : {written_ind:,} registros")
    print(f"  alertas          : {written_ale:,} eventos")
    print(f"  prediccion_ML    : {written_ml:,} registros")
    print(f"  Fecha poblada    : {fecha_local.strftime('%Y-%m-%d')} (Colombia)")
    print("=" * 65)
    print(f"\n✅ Ver en Grafana → http://localhost:3000")
    print(f"   Ajustar rango de tiempo a incluir {fecha_local.strftime('%Y-%m-%d')}")

    client.close()


if __name__ == "__main__":
    main()
