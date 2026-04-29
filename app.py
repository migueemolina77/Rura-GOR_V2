import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.4", layout="wide")
st.title("🚜 Plan Logístico Rubiales v3.4")

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
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        # Acceso por posición para evitar errores de nombres de columna
        # 1: CLUSTER, 3: ESTE, 4: NORTE
        df_coords = df.iloc[:, [1, 3, 4]].copy()
        df_coords.columns = ['NAME', 'E', 'N']
        
        df_coords['E'] = pd.to_numeric(df_coords['E'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['N'] = pd.to_numeric(df_coords['N'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords = df_coords.dropna()

        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lt, ln = proyectadas_a_latlon_manual(row['E'], row['N'])
            lats.append(lt); lons.append(ln)
        
        df_coords['lat'] = lats
        df_coords['lon'] = lons
        df_coords['KEY'] = df_coords['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_coords.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except: return pd.DataFrame()

# --- LÓGICA DE VISUALIZACIÓN ---
df_maestro = cargar_base_segura()

st.sidebar.header("📍 Control de Ruta")
txt_input = st.sidebar.text_area("Buscar Clústeres:", "")

puntos_a_mostrar = []

if not df_maestro.empty:
    # 1. Intentar buscar lo que el usuario escribió
    nombres_busqueda = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]
    
    for i, nombre in enumerate(nombres_busqueda):
        key = re.sub(r'[^a-zA-Z0-9]', '', nombre)
        match = df_maestro[df_maestro['KEY'] == key]
        if not match.empty:
            puntos_a_mostrar.append({
                'id': i+1, 'n': match.iloc[0]['NAME'], 
                'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon'],
                'color': 'red'
            })

    # 2. SI NO HAY BÚSQUEDA O NO SE ENCONTRÓ NADA, MOSTRAR POR DEFAULT
    if not puntos_a_mostrar:
        st.sidebar.warning("Mostrando puntos por defecto (Rubiales/Caño Sur)")
        # Tomamos los primeros 10 puntos del archivo para asegurar visualización
        defaults = df_maestro.head(10)
        for i, row in defaults.iterrows():
            puntos_a_mostrar.append({
                'id': "D", 'n': row['NAME'], 
                'lat': row['lat'], 'lon': row['lon'],
                'color': 'blue'
            })

# --- MAPA ---
# Centro inicial en el área de Rubiales
c_lat, c_lon = 3.99, -71.73 
if puntos_a_mostrar:
    c_lat, c_lon = puntos_a_mostrar[0]['lat'], puntos_a_mostrar[0]['lon']

m = folium.Map(location=[c_lat, c_lon], zoom_start=11)

for p in puntos_a_mostrar:
    folium.Marker(
        [p['lat'], p['lon']], 
        tooltip=p['n'], 
        icon=folium.Icon(color=p['color'], icon='location-pin')
    ).add_to(m)
    
    # Etiqueta flotante
    folium.map.Marker(
        [p['lat'], p['lon']],
        icon=DivIcon(icon_size=(25,25), icon_anchor=(-15,25),
        html=f'<div style="font-size: 9pt; color: white; background: {p["color"]}; border-radius: 3px; padding: 2px 5px; font-weight: bold; white-space: nowrap;">{p["n"]}</div>')
    ).add_to(m)

st_folium(m, width=1100, height=600, key="mapa_v34")

if not df_maestro.empty:
    with st.expander("Ver lista completa de pozos detectados"):
        st.write(df_maestro['NAME'].unique().tolist())
