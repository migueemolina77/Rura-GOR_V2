import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.3", layout="wide")
st.title("🚜 Plan Logístico Rubiales v3.3")

def proyectadas_a_latlon_manual(este, norte):
    try:
        # Origen Nacional Colombia (EPSG:9377)
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
def cargar_base_segura():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path): return pd.DataFrame()
    try:
        # Leemos el archivo
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        
        # --- SOLUCIÓN KEYERROR: ACCESO POR POSICIÓN ---
        # Columna 1 (índice 1): CLUSTER
        # Columna 3 (índice 3): ESTE
        # Columna 4 (índice 4): NORTE
        df_coords = df.iloc[:, [1, 3, 4]].copy()
        df_coords.columns = ['NAME', 'E', 'N'] # Renombramos internamente
        
        # Limpieza de números
        df_coords['E'] = pd.to_numeric(df_coords['E'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['N'] = pd.to_numeric(df_coords['N'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords = df_coords.dropna()

        # Conversión matemática
        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lt, ln = proyectadas_a_latlon_manual(row['E'], row['N'])
            lats.append(lt); lons.append(ln)
        
        df_coords['lat'] = lats
        df_coords['lon'] = lons
        
        # Llave de búsqueda simplificada
        df_coords['KEY'] = df_coords['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_coords.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df_maestro = cargar_base_segura()

st.sidebar.header("📍 Navegación Rubiales")
txt_input = st.sidebar.text_area("Ingresa Clústeres (ej: AGRIO-1):", "AGRIO-1\nCASE0015")

puntos_ruta = []
if not df_maestro.empty:
    nombres_busqueda = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]
    for i, nombre in enumerate(nombres_busqueda):
        key = re.sub(r'[^a-zA-Z0-9]', '', nombre)
        match = df_maestro[df_maestro['KEY'] == key]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'n': match.iloc[0]['NAME'], 
                'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']
            })

# Mapa
c_lat, c_lon = 3.99, -71.73 # Centro por defecto
if puntos_ruta:
    c_lat, c_lon = puntos_ruta[0]['lat'], puntos_ruta[0]['lon']

m = folium.Map(location=[c_lat, c_lon], zoom_start=12)

for p in puntos_ruta:
    folium.Marker([p['lat'], p['lon']], tooltip=p['n'], icon=folium.Icon(color='red')).add_to(m)
    folium.map.Marker([p['lat'], p['lon']],
        icon=DivIcon(icon_size=(25,25), icon_anchor=(-15,25),
        html=f'<div style="font-size: 10pt; color: white; background: red; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 1px solid white;">{p["id"]}</div>')).add_to(m)

st_folium(m, width=1100, height=550, key="mapa_v33")

# Tabla de ayuda si no encuentra nada
if not puntos_ruta and not df_maestro.empty:
    st.info("Escribe el nombre de un clúster válido. Aquí tienes algunos ejemplos de tu archivo:")
    st.write(df_maestro['NAME'].head(10).tolist())
