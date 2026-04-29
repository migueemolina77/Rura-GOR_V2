import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Diagnóstico Logística v3.2", layout="wide")
st.title("🚜 Inspector de Coordenadas Rubiales")

def proyectadas_a_latlon_manual(este, norte):
    try:
        # Parámetros Origen Nacional Colombia (EPSG:9377)
        lat_0, lon_0 = 4.0, -73.0
        f_este, f_norte = 5000000.0, 2000000.0
        scale, r_earth = 0.9992, 6378137.0
        d_norte = (norte - f_norte) / scale
        d_este = (este - f_este) / scale
        lat = lat_0 + (d_norte / r_earth) * (180.0 / math.pi)
        lon = lon_0 + (d_este / (r_earth * math.cos(math.radians(lat_0)))) * (180.0 / math.pi)
        return lat, lon
    except:
        return None, None

# 1. INTENTO DE CARGA CON DIAGNÓSTICO
path = "COORDENADAS_GOR.xlsx - data.csv"

if not os.path.exists(path):
    st.error(f"❌ ERROR: El archivo '{path}' no existe en la raíz del repositorio.")
    st.stop()

try:
    # Leemos el archivo crudo para ver qué hay dentro
    df_raw = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
    st.sidebar.success("✅ Archivo detectado")
    
    # Limpiamos columnas
    df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    
    # Mostramos las primeras filas en el sidebar para validar nombres de columnas
    with st.sidebar.expander("Ver estructura del CSV"):
        st.write("Columnas detectadas:", list(df_raw.columns))
        st.dataframe(df_raw.head(3))

    # Seleccionamos columnas por nombre (asegúrate que coincidan con tu Excel)
    # Si tu Excel usa otros nombres, cámbiados aquí:
    col_cluster = 'CLUSTER'
    col_este = 'ESTE'
    col_norte = 'NORTE'

    df_clean = df_raw[[col_cluster, col_este, col_norte]].copy()
    df_clean[col_este] = pd.to_numeric(df_clean[col_este].astype(str).str.replace(' ', ''), errors='coerce')
    df_clean[col_norte] = pd.to_numeric(df_clean[col_norte].astype(str).str.replace(' ', ''), errors='coerce')
    df_clean = df_clean.dropna()

    # Conversión
    lats, lons = [], []
    for _, row in df_clean.iterrows():
        lt, ln = proyectadas_a_latlon_manual(row[col_este], row[col_norte])
        lats.append(lt); lons.append(ln)
    
    df_clean['lat'] = lats
    df_clean['lon'] = lons
    
    # Key de búsqueda
    df_clean['KEY'] = df_clean[col_cluster].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
    df_maestro = df_clean.groupby(col_cluster).first().reset_index()

except Exception as e:
    st.error(f"❌ Error procesando el archivo: {e}")
    st.stop()

# --- INTERFAZ ---
txt_input = st.sidebar.text_area("Ingresa Clústeres (ej: AGRIO-1):", "AGRIO-1")
nombres_busqueda = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

puntos_ruta = []
st.subheader("🔍 Estado de la búsqueda")
cols = st.columns(len(nombres_busqueda) if nombres_busqueda else 1)

for i, nombre in enumerate(nombres_busqueda):
    key = re.sub(r'[^a-zA-Z0-9]', '', nombre)
    match = df_maestro[df_maestro['KEY'] == key]
    
    with cols[i % 3]: # Mostrar en columnas
        if not match.empty:
            p = {'id': i+1, 'n': match.iloc[0][col_cluster], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']}
            puntos_ruta.append(p)
            st.success(f"📍 {nombre}: ENCONTRADO\n({p['lat']:.4f}, {p['lon']:.4f})")
        else:
            st.error(f"❓ {nombre}: NO ENCONTRADO")

# MAPA
m = folium.Map(location=[4.0, -71.8], zoom_start=11)
if puntos_ruta:
    m.location = [puntos_ruta[0]['lat'], puntos_ruta[0]['lon']]
    for p in puntos_ruta:
        folium.Marker([p['lat'], p['lon']], tooltip=p['n'], icon=folium.Icon(color='red')).add_to(m)

st_folium(m, width=1100, height=500, key="mapa_diag")

# TABLA DE REFERENCIA FINAL
with st.expander("📋 Ver todos los Clústeres disponibles en tu archivo"):
    st.dataframe(df_maestro[[col_cluster, 'lat', 'lon']])
