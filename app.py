import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
from pyproj import Transformer
import os

st.set_page_config(page_title="Logística Rubiales v2.5", layout="wide")
st.title("🚜 Plan Logístico Rubiales v2.5")

# 1. Función de conversión (Magna-SIRGAS Origen Nacional -> WGS84)
def proyectadas_a_latlon(este, norte):
    try:
        # EPSG:9377 es el nuevo origen nacional único para Colombia
        transformer = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(float(este), float(norte))
        return lat, lon
    except:
        return None, None

@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        # Leemos el CSV
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Mapeo por posición (1:CLUSTER, 3:ESTE, 4:NORTE)
        df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # --- LIMPIEZA DIRECTA ---
        # Convertimos a string, quitamos espacios y luego a float
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'].astype(str).str.replace(' ', ''), errors='coerce')
        
        # Quitamos filas donde las coordenadas fallaron
        df_coords = df_coords.dropna(subset=['ESTE', 'NORTE'])
        
        # Aplicamos la transformación
        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lat, lon = proyectadas_a_latlon(row['ESTE'], row['NORTE'])
            lats.append(lat)
            lons.append(lon)
        
        df_coords['lat_dec'] = lats
        df_coords['lon_dec'] = lons
        
        # Limpiamos los que no se pudieron transformar
        df_coords = df_coords.dropna(subset=['lat_dec', 'lon_dec'])
        
        # Agrupar para el mapa
        df_final = df_coords.groupby('CLUSTER').agg({
            'lat_dec': 'first', 
            'lon_dec': 'first', 
            'POZO': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
        
        return df_final
    except Exception as e:
        st.error(f"Error procesando datos: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df_maestro = cargar_base()

if not df_maestro.empty:
    st.sidebar.success(f"Base cargada: {len(df_maestro)} clústeres")
    
    # Selector de ruta
    txt_input = st.sidebar.text_area("Ruta (Ingresa Clústeres):", "AGRIO-1\nCASE0015")
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres):
        match = df_maestro[df_maestro['CLUSTER'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 'lon': match.iloc[0]['lon_dec']
            })
        else:
            if nombre: st.sidebar.warning(f"⚠️ '{nombre}' no encontrado")

    # Mostrar Mapa
    # Iniciamos el mapa en el promedio de los puntos encontrados o en el centro de Rubiales
    if puntos_ruta:
        center_lat = sum(p['lat'] for p in puntos_ruta) / len(puntos_ruta)
        center_lon = sum(p['lon'] for p in puntos_ruta) / len(puntos_ruta)
        m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    else:
        m = folium.Map(location=[4.0, -72.0], zoom_start=10)

    # Dibujar marcadores y etiquetas
    for p in puntos_ruta:
        folium.Marker(
            [p['lat'], p['lon']], 
            tooltip=f"Parada {p['id']}: {p['nombre']}",
            icon=folium.Icon(color='blue', icon='truck', prefix='fa')
        ).add_to(m)
        
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(icon_size=(25,25), icon_anchor=(-15,25),
            html=f'<div style="font-size: 11pt; color: white; background: #007bff; border: 2px solid white; border-radius: 5px; padding: 2px 6px; font-weight: bold; box-shadow: 2px 2px 5px rgba(0,0,0,0.3);">{p["id"]}</div>')
        ).add_to(m)

    st_folium(m, width=1100, height=600)
    
    if not puntos_ruta:
        st.info("Ingresa nombres de clústeres en el panel izquierdo para ver la ruta.")
else:
    st.error("❌ No se pudieron procesar las coordenadas. Revisa que el archivo CSV esté en la raíz del repositorio.")
