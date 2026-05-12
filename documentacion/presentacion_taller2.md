# Estructura de Presentación — Taller 2: Data Lake Airbnb Chile

> Usar como guía para armar PPT/Canva/PDF. Cada sección = 1-2 slides.

---

## Slide 1: Portada
- **Título:** Data Lake — Mercado Airbnb Chile
- **Subtítulo:** Taller 2 — Tecnologías de la Información para la Gestión de Datos
- Nombres del equipo, fecha, universidad

---

## Slide 2: Contexto del Problema
- **Fuente de datos:** AirROI Data Portal (airroi.com)
- **Dominio:** Mercado de arriendos de corta estadía en Chile
- **Alcance:** 4 ciudades — Santiago, La Serena, Pucón, Viña del Mar
- **Período:** Mayo 2025 – Abril 2026 (12 meses)
- **Volumen:** ~1,200 propiedades, ~14,000 registros mensuales

---

## Slide 3: Diseño del Data Lake
- **Insertar el diagrama:** `Diseño Data Lake Airbnb.png`
- Explicar el flujo: Sources → Ingesta → Bronze → Limpieza → Silver
- Mencionar: Catálogo de Datos como componente transversal

---

## Slide 4: Capa Bronze — Datos Crudos
- **Motor:** Sistema de archivos local (directorio estructurado)
- **Nomenclatura:** `capa_bronce/chile/{ciudad}/{archivo}.csv`
- **Estructura:**
  ```
  capa_bronce/chile/
  ├── santiago/       (listing_data.csv + past_calendar.csv)
  ├── la_serena/      (listing_data.csv + past_calendar.csv)
  ├── pucon/          (listing_data.csv + past_calendar.csv)
  └── vina_del_mar/   (listing_data.csv + past_calendar.csv)
  ```
- **Patrones:** Datos crudos sin modificar, particionados por país → ciudad
- **2 datasets por ciudad:** Fichas de propiedades (73 cols) + Historial de reservas (14 cols)

---

## Slide 5: Capa Silver — Datos Limpios
- **Motor:** SQLite (base de datos relacional embebida)
- **Base de datos:** `capa_silver/airbnb_silver.db`
- **2 tablas:**
  - `listings_data` → 1,138 registros, 12 columnas (de 73 originales)
  - `past_calendar_rates` → 14,177 registros, 15 columnas
- **Campo derivado:** `ciudad` agregado para análisis comparativo
- **Índices:** Por ciudad, room_type, listing_id, date

---

## Slide 6: Problemas de Calidad Encontrados
- **Filas corruptas:** Campo `description` con HTML roto desplaza columnas (~25% en Santiago)
- **Datos basura:** room_type con URLs, currency con valores numéricos inválidos
- **NULLs significativos:** bedrooms (7%), guests (7%), métricas de reserva (43-46%)
- **Duplicados:** 5 en Viña del Mar
- **IDs huérfanos:** 5.2% de registros en calendar sin match en listings

---

## Slide 7: Estrategia de Limpieza (Transformaciones)
- **Filas corruptas** → Parser tolerante + skip + log de omitidas
- **Datos basura** → Filtro por valores válidos de room_type
- **NULLs numéricos** → **Mantener NULL** (0 dormitorios ≠ "dato no disponible")
- **NULLs de reserva** → **Mantener NULL** (meses sin reservas → sin tarifa)
- **host_name vacío** → Reemplazar con "Desconocido"
- **Duplicados** → Mantener primera ocurrencia
- **Columnas** → Reducción de 73 → 12 columnas relevantes

---

## Slide 8: ETL — Pipeline de Carga
- **Tecnología:** Python (pandas + sqlite3)
- **Fases:** Extract → Transform → Load → Validate
- **Características:**
  - Modular (funciones separadas por fase)
  - Idempotente (se puede re-ejecutar sin problemas)
  - Logging detallado a archivo
  - Validación automática post-carga
- **Tiempo de ejecución:** ~2 segundos

---

## Slide 9: Validación de Resultados
| Métrica | Resultado |
|---|---|
| Listings en Silver | 1,138 (de ~1,200 en Bronze) |
| Calendar en Silver | 14,177 |
| Tasa de match referencial | 94.8% |
| Top propiedad (ingresos) | Pucón: $38,073 USD/año |
| Ciudad más ocupada | Santiago: hasta 90.4% ocupación |

---

## Slide 10: Catálogo de Datos
- **Archivo:** `catalogo_datos_datalake.xlsx`
- **4 hojas:**
  1. Catálogo Bronze (columnas originales, tipos, clasificación)
  2. Catálogo Silver (columnas limpias, restricciones, transformaciones)
  3. Catálogo de Fuentes (origen, periodicidad, volumen)
  4. Linaje de Datos (mapeo Bronze → Silver con transformación aplicada)

---

## Slide 11: Estructura Final del Proyecto
```
TIDATOS/
├── capa_bronce/chile/{4 ciudades}/     ← Datos crudos (CSV)
├── capa_silver/airbnb_silver.db        ← Datos limpios (SQLite)
├── etl_bronze_to_silver.py             ← Pipeline ETL
├── generar_catalogo.py                 ← Generador de catálogo
├── requirements.txt                    ← Dependencias
├── catalogo_datos_datalake.xlsx        ← Catálogo consolidado
├── Diseño Data Lake Airbnb.png         ← Diagrama de diseño
└── documentacion/etl_log_*.txt         ← Logs de ejecución
```

---

## Slide 12: Conclusiones y Aprendizajes
- La calidad de los datos crudos impacta directamente el diseño del ETL
- Los NULLs no siempre deben rellenarse — depende del significado semántico
- Un catálogo de datos bien documentado facilita la toma de decisiones
- SQLite es ideal como capa Silver para volúmenes moderados sin infraestructura
- El logging y la validación automática son fundamentales para la confianza en los datos
