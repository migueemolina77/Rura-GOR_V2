import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
from pyproj import Transformer
import os

st.set_page_config(page_title="Logística Rubiales v2.4", layout="wide")
st.title("🚜 Plan Logístico Rubiales v2.4")

def proyectadas_a_latlon(este, norte):
    try:
        # Origen Nacional Colombia EPSG:9377
        transformer = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(float(este), float(norte))
        return lat, lon
    except:
        return None, None

def limpiar_numero_colombiano(valor):
    """Convierte '5.147.414,36' a 5147414.36"""
    if pd.isna(valor): return None
    s = str(valor).strip()
    s = s.replace('.', '')  # Quita puntos de miles
    s = s.replace(',', '.')  # Cambia coma decimal por punto
    try:
        return float(s)
    except:
        return None

@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Extraer columnas por posición (1:CLUSTER, 3:ESTE, 4:NORTE)
        df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # --- LIMPIEZA CRÍTICA ---
        df_coords['ESTE_LIMPIO'] = df_coords['ESTE'].apply(limpiar_numero_colombiano)
        df_coords['NORTE_LIMPIO'] = df_coords['NORTE'].apply(limpiar_numero_colombiano)
        
        df_coords = df_coords.dropna(subset=['ESTE_LIMPIO', 'NORTE_LIMPIO'])
        
        # Transformación
        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lat, lon = proyectadas_a_latlon(row['ESTE_LIMPIO'], row['NORTE_LIMPIO'])
            lats.append(lat)
            lons.append(lon)
        
        df_coords['lat_dec'] = lats
        df_coords['lon_dec'] = lons
        
        # Agrupar por Clúster para el mapa
        df_final = df_coords.dropna(subset=['lat_dec']).groupby('CLUSTER').agg({
            'lat_dec': 'first', 
            'lon_dec': 'first', 
            'POZO': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
        
        return df_final
    except Exception as e:
        st.error(f"Error técnico: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df_maestro = cargar_base()

if not df_maestro.empty:
    st.sidebar.success(f"Base lista: {len(df_maestro)} clústeres")
    txt_input = st.sidebar.text_area("Ruta (Clústeres):", "AGRIO-1\nCASE0015")
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres):
        match = df_maestro[df_maestro['CLUSTER'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 'lon': match.iloc[0]['lon_dec']
            })

    # Centro del mapa en Rubiales
    m = folium.Map(location=[4.0, -72.0], zoom_start=10) 
    if not df_maestro.empty:
        m.location = [df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()]

    # Dibujar
    for p in puntos_ruta:
        folium.Marker(
            [p['lat'], p['lon']], 
            tooltip=p['nombre'],
            icon=folium.Icon(color='red', icon='truck', prefix='fa')
        ).add_to(m)
        
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(icon_size=(20,20), icon_anchor=(-10,20),
            html=f'<div style="font-size: 10pt; color: black; background: white; border: 2px solid red; border-radius: 50%; width: 25px; height: 25px; display: flex; align-items: center; justify-content: center; font-weight: bold;">{p["id"]}</div>')
        ).add_to(m)

    st_folium(m, width=1000, height=500)
else:
    st.warning("No se pudieron procesar las coordenadas. Verifica el formato del CSV.")
