"""
ETL Bronze → Silver | Data Lake Airbnb Chile
=============================================
Taller 2 — Tecnologías de la Información para la gestión de Datos

Este script extrae los datos crudos de la capa Bronze (CSVs),
los transforma (limpieza y estandarización) y los carga en la
capa Silver (base de datos SQLite).

Uso:
    python etl_bronze_to_silver.py

Estructura esperada en Bronze:
    capa_bronce/chile/{ciudad}/listing_data.csv
    capa_bronce/chile/{ciudad}/past_calendar.csv
"""

import os
import sqlite3
import logging
from datetime import datetime

import pandas as pd

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Rutas
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "capa_bronce", "chile")
SILVER_DIR = os.path.join(BASE_DIR, "capa_silver")
SILVER_DB = os.path.join(SILVER_DIR, "airbnb_silver.db")
DOC_DIR = os.path.join(BASE_DIR, "documentacion")

# Columnas Silver para listings (selección del catálogo de datos)
LISTING_SILVER_COLS = [
    "listing_id",
    "listing_name",
    "latitude",
    "longitude",
    "host_name",
    "superhost",
    "room_type",
    "bedrooms",
    "beds",
    "baths",
    "guests",
    "currency",
    "num_reviews",
    "rating_overall",
]

# Valores válidos para room_type
VALID_ROOM_TYPES = {"entire_home", "private_room", "hotel_room", "shared_room"}

# Columnas Silver para past_calendar (todas las originales)
CALENDAR_SILVER_COLS = [
    "listing_id",
    "date",
    "vacant_days",
    "reserved_days",
    "occupancy",
    "revenue",
    "rate_avg",
    "booked_rate_avg",
    "booking_lead_time_avg",
    "length_of_stay_avg",
    "min_nights_avg",
    "native_booked_rate_avg",
    "native_rate_avg",
    "native_revenue",
]


# =============================================================================
# LOGGING
# =============================================================================

def setup_logging():
    """Configura logging a consola y a archivo en documentacion/."""
    os.makedirs(DOC_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(DOC_DIR, f"etl_log_{timestamp}.txt")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.info(f"Log guardado en: {log_file}")
    return log_file


# =============================================================================
# EXTRACT — Lectura de datos desde Bronze
# =============================================================================

def extract_listings(ciudad: str) -> pd.DataFrame:
    """
    Lee listing_data.csv de una ciudad.
    Usa engine='python' para manejar filas con HTML roto en description.
    """
    path = os.path.join(BRONZE_DIR, ciudad, "listing_data.csv")
    logging.info(f"  Leyendo listings: {path}")

    # Contar líneas totales del archivo (excluyendo header)
    with open(path, "r", encoding="utf-8") as f:
        total_lines = sum(1 for _ in f) - 1

    # Leer con parser tolerante a errores
    df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    skipped = total_lines - len(df)

    logging.info(f"    → {len(df)} filas leídas, {skipped} filas omitidas por formato corrupto")
    if skipped > 0:
        logging.warning(f"    ⚠ {skipped} filas tenían HTML en 'description' que rompió el parseo CSV")

    return df


def extract_calendar(ciudad: str) -> pd.DataFrame:
    """Lee past_calendar.csv de una ciudad."""
    path = os.path.join(BRONZE_DIR, ciudad, "past_calendar.csv")
    logging.info(f"  Leyendo calendar: {path}")

    df = pd.read_csv(path)
    logging.info(f"    → {len(df)} filas leídas")
    return df


def extract_all() -> tuple:
    """
    Extrae datos de todas las ciudades en Bronze.
    Retorna (listings_list, calendar_list) con DataFrames por ciudad.
    """
    ciudades = sorted([
        d for d in os.listdir(BRONZE_DIR)
        if os.path.isdir(os.path.join(BRONZE_DIR, d))
    ])
    logging.info(f"Ciudades detectadas en Bronze: {ciudades}")

    listings_all = []
    calendar_all = []

    for ciudad in ciudades:
        logging.info(f"\n📂 Extrayendo datos de: {ciudad}")
        listings_df = extract_listings(ciudad)
        listings_df["ciudad"] = ciudad  # Campo derivado
        listings_all.append(listings_df)

        calendar_df = extract_calendar(ciudad)
        calendar_df["ciudad"] = ciudad  # Campo derivado
        calendar_all.append(calendar_df)

    return listings_all, calendar_all


# =============================================================================
# TRANSFORM — Limpieza y estandarización
# =============================================================================

def transform_listings(dfs: list) -> pd.DataFrame:
    """
    Transforma y limpia los DataFrames de listings.

    Transformaciones aplicadas:
    1. Seleccionar solo columnas Silver
    2. Filtrar filas con listing_id no numérico (filas desplazadas por HTML)
    3. Filtrar room_type con valores inválidos (URLs, basura)
    4. Eliminar duplicados por listing_id
    5. Rellenar host_name vacío con 'Desconocido'
    6. Castear tipos de datos
    """
    logging.info("\n🔧 TRANSFORMANDO LISTINGS")

    df = pd.concat(dfs, ignore_index=True)
    logging.info(f"  Total combinado (bruto): {len(df)} filas")

    # 1. Seleccionar columnas Silver + ciudad
    cols = LISTING_SILVER_COLS + ["ciudad"]
    df = df[cols].copy()

    # 2. Filtrar listing_id no numérico (filas corruptas por HTML)
    df["listing_id"] = pd.to_numeric(df["listing_id"], errors="coerce")
    invalid_ids = df["listing_id"].isna().sum()
    df = df.dropna(subset=["listing_id"])
    df["listing_id"] = df["listing_id"].astype(int)
    if invalid_ids > 0:
        logging.warning(f"  ⚠ {invalid_ids} filas eliminadas por listing_id no numérico")

    # 3. Filtrar room_type inválido (URLs, datos desplazados)
    invalid_room = ~df["room_type"].isin(VALID_ROOM_TYPES)
    n_invalid_room = invalid_room.sum()
    df = df[~invalid_room]
    if n_invalid_room > 0:
        logging.warning(f"  ⚠ {n_invalid_room} filas eliminadas por room_type inválido")

    # 4. Eliminar duplicados por listing_id (mantener primera ocurrencia)
    n_before = len(df)
    df = df.drop_duplicates(subset=["listing_id"], keep="first")
    n_dups = n_before - len(df)
    if n_dups > 0:
        logging.warning(f"  ⚠ {n_dups} duplicados eliminados por listing_id")

    # 5. Rellenar host_name vacío
    n_host_null = df["host_name"].isna().sum()
    df["host_name"] = df["host_name"].fillna("Desconocido")
    if n_host_null > 0:
        logging.info(f"  ✏️ {n_host_null} host_name NULL → 'Desconocido'")

    # 6. Mantener NULLs en bedrooms, beds, baths, guests (decisión semántica)
    for col in ["bedrooms", "beds", "baths", "guests"]:
        n_null = df[col].isna().sum()
        if n_null > 0:
            pct = round(n_null / len(df) * 100, 1)
            logging.info(f"  ℹ️ {col}: {n_null} NULLs mantenidos ({pct}%) — dato no disponible")

    logging.info(f"  ✅ Listings transformados: {len(df)} filas finales")
    return df


def transform_calendar(dfs: list) -> pd.DataFrame:
    """
    Transforma y limpia los DataFrames de past_calendar.

    Transformaciones aplicadas:
    1. Seleccionar columnas Silver
    2. Validar listing_id numérico
    3. Validar formato de fecha
    4. Eliminar duplicados por (listing_id, date, ciudad)
    5. Castear tipos
    """
    logging.info("\n🔧 TRANSFORMANDO PAST CALENDAR")

    df = pd.concat(dfs, ignore_index=True)
    logging.info(f"  Total combinado (bruto): {len(df)} filas")

    # 1. Seleccionar columnas Silver + ciudad
    cols = CALENDAR_SILVER_COLS + ["ciudad"]
    df = df[cols].copy()

    # 2. Validar listing_id numérico
    df["listing_id"] = pd.to_numeric(df["listing_id"], errors="coerce")
    invalid_ids = df["listing_id"].isna().sum()
    df = df.dropna(subset=["listing_id"])
    df["listing_id"] = df["listing_id"].astype(int)
    if invalid_ids > 0:
        logging.warning(f"  ⚠ {invalid_ids} filas eliminadas por listing_id no numérico")

    # 3. Validar formato de fecha (YYYY-MM-DD)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    invalid_dates = df["date"].isna().sum()
    df = df.dropna(subset=["date"])
    if invalid_dates > 0:
        logging.warning(f"  ⚠ {invalid_dates} filas eliminadas por fecha inválida")

    # 4. Eliminar duplicados
    n_before = len(df)
    df = df.drop_duplicates(subset=["listing_id", "date", "ciudad"], keep="first")
    n_dups = n_before - len(df)
    if n_dups > 0:
        logging.warning(f"  ⚠ {n_dups} duplicados eliminados por (listing_id, date, ciudad)")

    # 5. NULLs semánticos — mantener (meses sin reservas)
    null_cols = ["booked_rate_avg", "booking_lead_time_avg", "length_of_stay_avg",
                 "min_nights_avg", "native_booked_rate_avg"]
    for col in null_cols:
        n_null = df[col].isna().sum()
        if n_null > 0:
            pct = round(n_null / len(df) * 100, 1)
            logging.info(f"  ℹ️ {col}: {n_null} NULLs mantenidos ({pct}%) — meses sin reservas")

    logging.info(f"  ✅ Calendar transformado: {len(df)} filas finales")
    return df


# =============================================================================
# LOAD — Carga en SQLite (Capa Silver)
# =============================================================================

def load_to_sqlite(listings_df: pd.DataFrame, calendar_df: pd.DataFrame):
    """
    Carga los DataFrames transformados en la base de datos SQLite.
    Modo 'replace' para que sea idempotente (se puede re-ejecutar).
    """
    logging.info("\n💾 CARGANDO EN CAPA SILVER (SQLite)")

    os.makedirs(SILVER_DIR, exist_ok=True)
    logging.info(f"  Base de datos: {SILVER_DB}")

    conn = sqlite3.connect(SILVER_DB)

    try:
        # Cargar listings
        listings_df.to_sql("listings_data", conn, if_exists="replace", index=False)
        logging.info(f"  ✅ Tabla 'listings_data' cargada: {len(listings_df)} registros")

        # Cargar calendar
        calendar_df.to_sql("past_calendar_rates", conn, if_exists="replace", index=False)
        logging.info(f"  ✅ Tabla 'past_calendar_rates' cargada: {len(calendar_df)} registros")

        # Crear índices para mejorar rendimiento de consultas
        cursor = conn.cursor()
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_listings_ciudad ON listings_data(ciudad)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_listings_room ON listings_data(room_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_calendar_listing ON past_calendar_rates(listing_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_calendar_ciudad ON past_calendar_rates(ciudad)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_calendar_date ON past_calendar_rates(date)")
        conn.commit()
        logging.info("  ✅ Índices creados")

    finally:
        conn.close()


# =============================================================================
# VALIDATE — Validación post-carga
# =============================================================================

def validate():
    """
    Ejecuta validaciones sobre la base de datos Silver:
    1. Conteo de registros por tabla y ciudad
    2. Integridad referencial
    3. Query de ejemplo
    """
    logging.info("\n🔍 VALIDACIÓN POST-CARGA")

    conn = sqlite3.connect(SILVER_DB)

    try:
        # 1. Conteo por tabla y ciudad
        logging.info("\n  📊 Conteo de registros:")
        for tabla in ["listings_data", "past_calendar_rates"]:
            total = pd.read_sql(f"SELECT COUNT(*) as n FROM {tabla}", conn).iloc[0, 0]
            por_ciudad = pd.read_sql(
                f"SELECT ciudad, COUNT(*) as registros FROM {tabla} GROUP BY ciudad ORDER BY ciudad",
                conn
            )
            logging.info(f"\n  Tabla '{tabla}' — Total: {total}")
            for _, row in por_ciudad.iterrows():
                logging.info(f"    • {row['ciudad']}: {row['registros']} registros")

        # 2. Integridad referencial
        orphans = pd.read_sql("""
            SELECT c.ciudad, COUNT(DISTINCT c.listing_id) as ids_huerfanos
            FROM past_calendar_rates c
            LEFT JOIN listings_data l ON c.listing_id = l.listing_id
            WHERE l.listing_id IS NULL
            GROUP BY c.ciudad
            ORDER BY c.ciudad
        """, conn)

        logging.info("\n  🔗 Integridad referencial (listing_id en calendar sin match en listings):")
        if len(orphans) == 0:
            logging.info("    ✅ Todos los listing_id en calendar existen en listings")
        else:
            for _, row in orphans.iterrows():
                logging.warning(f"    ⚠ {row['ciudad']}: {row['ids_huerfanos']} IDs huérfanos")

        total_orphans = pd.read_sql("""
            SELECT COUNT(*) as n FROM past_calendar_rates c
            LEFT JOIN listings_data l ON c.listing_id = l.listing_id
            WHERE l.listing_id IS NULL
        """, conn).iloc[0, 0]

        total_calendar = pd.read_sql("SELECT COUNT(*) as n FROM past_calendar_rates", conn).iloc[0, 0]
        pct_match = round((1 - total_orphans / total_calendar) * 100, 1)
        logging.info(f"    → Tasa de match: {pct_match}% ({total_calendar - total_orphans}/{total_calendar})")

        # 3. Query de ejemplo: Top 5 propiedades por ingresos por ciudad
        logging.info("\n  🏆 Top 3 propiedades por ingresos totales (USD) por ciudad:")
        top = pd.read_sql("""
            SELECT
                c.ciudad,
                l.listing_name,
                l.room_type,
                ROUND(SUM(c.revenue), 2) as ingresos_totales_usd,
                ROUND(AVG(c.occupancy) * 100, 1) as ocupacion_promedio_pct
            FROM past_calendar_rates c
            INNER JOIN listings_data l ON c.listing_id = l.listing_id
            GROUP BY c.ciudad, c.listing_id
            ORDER BY c.ciudad, ingresos_totales_usd DESC
        """, conn)

        for ciudad in top["ciudad"].unique():
            logging.info(f"\n    📍 {ciudad}:")
            ciudad_top = top[top["ciudad"] == ciudad].head(3)
            for i, (_, row) in enumerate(ciudad_top.iterrows(), 1):
                name = row["listing_name"][:50] if len(str(row["listing_name"])) > 50 else row["listing_name"]
                logging.info(
                    f"      {i}. {name} | {row['room_type']} | "
                    f"${row['ingresos_totales_usd']:,.0f} USD | "
                    f"{row['ocupacion_promedio_pct']}% ocup."
                )

        # 4. Resumen de NULLs en Silver
        logging.info("\n  📋 Resumen de NULLs en Silver:")
        for tabla in ["listings_data", "past_calendar_rates"]:
            cols_info = pd.read_sql(f"PRAGMA table_info({tabla})", conn)
            col_names = cols_info["name"].tolist()
            for col in col_names:
                n_null = pd.read_sql(
                    f"SELECT COUNT(*) as n FROM {tabla} WHERE {col} IS NULL", conn
                ).iloc[0, 0]
                if n_null > 0:
                    total = pd.read_sql(f"SELECT COUNT(*) as n FROM {tabla}", conn).iloc[0, 0]
                    pct = round(n_null / total * 100, 1)
                    logging.info(f"    {tabla}.{col}: {n_null} NULLs ({pct}%)")

    finally:
        conn.close()


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Ejecuta el pipeline ETL completo: Extract → Transform → Load → Validate."""
    log_file = setup_logging()

    logging.info("=" * 70)
    logging.info("  ETL BRONZE → SILVER | Data Lake Airbnb Chile")
    logging.info("=" * 70)
    logging.info(f"  Fecha de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"  Bronze: {BRONZE_DIR}")
    logging.info(f"  Silver: {SILVER_DB}")
    logging.info("=" * 70)

    start_time = datetime.now()

    # EXTRACT
    logging.info("\n" + "=" * 70)
    logging.info("  FASE 1: EXTRACCIÓN (Bronze → DataFrames)")
    logging.info("=" * 70)
    listings_list, calendar_list = extract_all()

    # TRANSFORM
    logging.info("\n" + "=" * 70)
    logging.info("  FASE 2: TRANSFORMACIÓN (Limpieza y Estandarización)")
    logging.info("=" * 70)
    listings_clean = transform_listings(listings_list)
    calendar_clean = transform_calendar(calendar_list)

    # LOAD
    logging.info("\n" + "=" * 70)
    logging.info("  FASE 3: CARGA (DataFrames → SQLite)")
    logging.info("=" * 70)
    load_to_sqlite(listings_clean, calendar_clean)

    # VALIDATE
    logging.info("\n" + "=" * 70)
    logging.info("  FASE 4: VALIDACIÓN")
    logging.info("=" * 70)
    validate()

    # Resumen final
    elapsed = (datetime.now() - start_time).total_seconds()
    logging.info("\n" + "=" * 70)
    logging.info(f"  ✅ ETL COMPLETADO en {elapsed:.1f} segundos")
    logging.info(f"  📁 Base de datos Silver: {SILVER_DB}")
    logging.info(f"  📄 Log completo: {log_file}")
    logging.info("=" * 70)


if __name__ == "__main__":
    main()
