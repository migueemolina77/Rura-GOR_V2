import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.7", layout="wide")
st.title("🚜 Sistema Logístico Rubiales v3.7")

def proyectadas_a_latlon_manual(este, norte):
    try:
        lat_0, lon_0 = 4.0, -73.0
        f_este, f_norte = 5000000.0, 2000000.0
        scale, r_earth = 0.9992, 6378137.0
        d_norte = (norte - f_norte) / scale
        d_este = (este - f_este) / scale
        lat = lat_0 + (d_norte / r_earth) * (180.0 / math.pi)
        lon = lon_0 + (d_este / (r_earth * math.cos(math.radians(lat_0)))) * (180.0 / math.pi)
        return lat, lon
    except: return None, None

@st.cache_data
def procesar_datos_blindado(file_source):
    try:
        # Intentamos leer con separador automático (coma, punto y coma o tab)
        df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        
        # Limpiamos nombres de columnas de cualquier caracter extraño
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        
        # Buscamos las columnas que contengan las palabras clave
        col_c = next((c for c in df.columns if 'CLUSTER' in c), None)
        col_e = next((c for c in df.columns if 'ESTE' in c), None)
        col_n = next((c for c in df.columns if 'NORTE' in c), None)

        if not col_c or not col_e or not col_n:
            st.error(f"⚠️ Columnas no encontradas. El archivo tiene: {list(df.columns)}")
            return pd.DataFrame()

        df_final = df[[col_c, col_e, col_n]].copy()
        df_final.columns = ['NAME', 'E', 'N']
        
        # Convertir a número quitando cualquier cosa que no sea dígito o punto
        for col in ['E', 'N']:
            df_final[col] = df_final[col].astype(str).str.replace(r'[^0-9.]', '', regex=True)
            df_final[col] = pd.to_numeric(df_final[col], errors='coerce')
        
        df_final = df_final.dropna()

        lats, lons = [], []
        for _, row in df_final.iterrows():
            lt, ln = proyectadas_a_latlon_manual(row['E'], row['N'])
            lats.append(lt); lons.append(ln)
        
        df_final['lat'], df_final['lon'] = lats, lons
        df_final['KEY'] = df_final['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_final.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except Exception as e:
        st.error(f"Error de lectura: {e}")
        return pd.DataFrame()

# --- CARGA ---
archivo_subido = st.sidebar.file_uploader("Sube el CSV aquí:", type=["csv"])
path_repo = "COORDENADAS_GOR.xlsx - data.csv"

df_maestro = pd.DataFrame()
if archivo_subido:
    df_maestro = procesar_datos_blindado(archivo_subido)
elif os.path.exists(path_repo):
    df_maestro = procesar_datos_blindado(path_repo)

# --- MAPA ---
puntos = []
if not df_maestro.empty:
    st.sidebar.success(f"✅ {len(df_maestro)} puntos cargados")
    busqueda = st.sidebar.text_area("Ruta (Nombres):", "AGRIO-1")
    
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    for i, n in enumerate(nombres):
        k = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_maestro[df_maestro['KEY'] == k]
        if not match.empty:
            puntos.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon'], 'color': 'red'})

    # Si no hay búsqueda, mostrar 5 de prueba
    if not puntos:
        for i, row in df_maestro.head(5).iterrows():
            puntos.append({'id': '•', 'n': row['NAME'], 'lat': row['lat'], 'lon': row['lon'], 'color': 'blue'})

m = folium.Map(location=[3.99, -71.73], zoom_start=11)
for p in puntos:
    folium.Marker([p['lat'], p['lon']], tooltip=p['n'], icon=folium.Icon(color=p['color'])).add_to(m)
    folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(icon_size=(20,20), icon_anchor=(-15,20),
        html=f'<div style="font-size: 9pt; color: white; background: {p["color"]}; border-radius: 4px; padding: 2px 5px; font-weight: bold;">{p["n"]}</div>')).add_to(m)

st_folium(m, width=1100, height=600, key="mapa_v37")

if not df_maestro.empty:
    with st.expander("Lista de Clústeres detectados"):
        st.write(df_maestro['NAME'].tolist())
