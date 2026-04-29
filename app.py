import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.0", layout="wide")
st.title("🚜 Plan Logístico Rubiales v3.0")

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
        
        # Validar que no sean números locos
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None, None
        return lat, lon
    except:
        return None, None

@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path): return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Tomamos CLUSTER(1), ESTE(3), NORTE(4)
        df_coords = df.iloc[:, [1, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'ESTE', 'NORTE']
        
        # Limpieza rigurosa
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords = df_coords.dropna()

        # Conversión
        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lt, ln = proyectadas_a_latlon_manual(row['ESTE'], row['NORTE'])
            lats.append(lt); lons.append(ln)
        
        df_coords['lat_dec'] = lats
        df_coords['lon_dec'] = lons
        
        # Agrupar y asegurar que no haya nulos antes de entregar
        return df_coords.dropna(subset=['lat_dec', 'lon_dec']).groupby('CLUSTER').first().reset_index()
    except Exception as e:
        st.error(f"Error en carga: {e}")
        return pd.DataFrame()

# --- LÓGICA DE INTERFAZ ---
df_maestro = cargar_base()

# Sidebar
st.sidebar.header("Configuración de Ruta")
txt_input = st.sidebar.text_area("Clústeres (uno por línea):", "AGRIO-1\nCASE0015")
nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

puntos_ruta = []
if not df_maestro.empty:
    for i, n in enumerate(nombres):
        m = df_maestro[df_maestro['CLUSTER'].str.upper() == n]
        if not m.empty:
            puntos_ruta.append({
                'id': i+1, 
                'n': n, 
                'lat': float(m.iloc[0]['lat_dec']), 
                'lon': float(m.iloc[0]['lon_dec'])
            })

# Creación del Mapa (Pre-validado)
# Coordenadas base de Rubiales/Puerto Gaitán por si no hay puntos
centro_lat, centro_lon = 3.99, -71.73 

if puntos_ruta:
    centro_lat = sum(p['lat'] for p in puntos_ruta) / len(puntos_ruta)
    centro_lon = sum(p['lon'] for p in puntos_ruta) / len(puntos_ruta)

m = folium.Map(location=[centro_lat, centro_lon], zoom_start=11, tiles="OpenStreetMap")

# Añadir marcadores solo si hay puntos válidos
for p in puntos_ruta:
    folium.Marker(
        [p['lat'], p['lon']], 
        tooltip=f"Parada {p['id']}: {p['n']}",
        icon=folium.Icon(color='blue', icon='info-sign')
    ).add_to(m)
    
    folium.map.Marker(
        [p['lat'], p['lon']],
        icon=DivIcon(icon_size=(30,30), icon_anchor=(-15,30),
        html=f'<div style="font-size: 12pt; color: white; background: #2980b9; border-radius: 5px; padding: 3px; font-weight: bold; border: 1px solid white;">{p["id"]}</div>')
    ).add_to(m)

# Renderizado final
st_folium(m, width=1100, height=600, key="mapa_rubiales")

if not puntos_ruta and not df_maestro.empty:
    st.info("Escribe nombres de clústeres válidos para ver la ruta.")
elif df_maestro.empty:
    st.error("No se pudo cargar la base de datos COORDENADAS_GOR.xlsx - data.csv")
