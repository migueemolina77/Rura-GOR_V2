import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v2.9", layout="wide")
st.title("🚜 Plan Logístico Rubiales v2.9")

def proyectadas_a_latlon_manual(este, norte):
    """
    Conversión calibrada para Origen Nacional (EPSG:9377) 
    Específicamente ajustada para la zona de Puerto Gaitán / Rubiales.
    """
    try:
        # Parámetros oficiales Origen Nacional Colombia (9377)
        lat_0 = 4.0
        lon_0 = -73.0
        # Estos son los falsos Este y Norte que desplazan el punto del océano a Colombia
        falso_este = 5000000.0
        falso_norte = 2000000.0
        
        # Factor de escala y radio de la tierra
        scale = 0.9992
        r_earth = 6378137.0 # Elipsoide WGS84

        # Diferenciales en metros
        d_norte = (norte - falso_norte) / scale
        d_este = (este - falso_este) / scale

        # Conversión a grados (aproximación local precisa)
        lat = lat_0 + (d_norte / r_earth) * (180.0 / math.pi)
        # La longitud depende del coseno de la latitud para ser precisa
        lon = lon_0 + (d_este / (r_earth * math.cos(math.radians(lat_0)))) * (180.0 / math.pi)
        
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
        df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # Limpiar y convertir
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords = df_coords.dropna(subset=['ESTE', 'NORTE'])
        
        # Transformar
        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lt, ln = proyectadas_a_latlon_manual(row['ESTE'], row['NORTE'])
            lats.append(lt); lons.append(ln)
        
        df_coords['lat_dec'] = lats
        df_coords['lon_dec'] = lons
        return df_coords.dropna(subset=['lat_dec']).groupby('CLUSTER').first().reset_index()
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df_maestro = cargar_base()

if not df_maestro.empty:
    st.sidebar.info("Base cargada correctamente.")
    txt_input = st.sidebar.text_area("Ruta de Clústeres:", "AGRIO-1\nCASE0015")
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

    puntos_ruta = []
    for i, n in enumerate(nombres):
        m = df_maestro[df_maestro['CLUSTER'].str.upper() == n]
        if not m.empty:
            puntos_ruta.append({'id': i+1, 'n': n, 'lat': m.iloc[0]['lat_dec'], 'lon': m.iloc[0]['lon_dec']})

    # Mapa centrado en los puntos
    if puntos_ruta:
        m = folium.Map(location=[puntos_ruta[0]['lat'], puntos_ruta[0]['lon']], zoom_start=12)
        for p in puntos_ruta:
            folium.Marker([p['lat'], p['lon']], tooltip=p['n']).add_to(m)
            folium.map.Marker([p['lat'], p['lon']], 
                icon=DivIcon(icon_size=(20,20), icon_anchor=(-10,20),
                html=f'<div style="font-size: 10pt; color: white; background: blue; border-radius: 5px; padding: 2px;">{p["id"]}</div>')).add_to(m)
    else:
        # Fallback a ubicación central de Rubiales
        m = folium.Map(location=[3.9, -71.8], zoom_start=10)

    st_folium(m, width=1000, height=500)
