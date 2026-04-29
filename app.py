import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v4.0", layout="wide")
st.title("🚜 Precisión Total: Magna-SIRGAS Este-Este")

# --- MOTOR DE GEORREFERENCIACIÓN CALIBRADO: ESTE-ESTE ---
def proyectadas_a_latlon_esteeste(este, norte):
    """
    Convierte Magna-SIRGAS Este-Este (antiguo) a WGS84.
    Esta es la proyección correcta para el descuadre en Rubiales.
    """
    try:
        # Constantes del elipsoide GRS80 (Magna-SIRGAS)
        a = 6378137.0
        f = 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        
        # --- PARÁMETROS CRÍTICOS ZONA ESTE-ESTE ---
        # Origen: Bogotá
        lat0_deg = 4.596200417
        lon0_deg = -71.077507917 # Origen Longitudinal Este-Este
        k0 = 1.000000000 # Factor de escala en el origen
        FE = 1000000.0   # Falso Este
        FN = 1000000.0   # Falso Norte
        # ------------------------------------------
        
        lat0 = lat0_deg * math.pi / 180.0
        lon0 = lon0_deg * math.pi / 180.0
        
        # Cálculos de proyección Transverse Mercator Inversa
        M0 = a * ((1 - e2/4 - 3*e2**2/64 - 5*e2**3/256)*lat0 - (3*e2/8 + 3*e2**2/32 + 45*e2**3/1024)*math.sin(2*lat0) + (15*e2**2/256 + 45*e2**3/1024)*math.sin(4*lat0) - (35*e2**3/3072)*math.sin(6*lat0))
        M = M0 + (norte - FN) / k0
        mu = M / (a * (1 - e2/4 - 3*e2**2/64 - 5*e2**3/256))
        e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
        
        phi1 = mu + (3*e1/2 - 27*e1**3/32)*math.sin(2*mu) + (21*e1**2/16 - 55*e1**4/32)*math.sin(4*mu) + (151*e1**3/96)*math.sin(6*mu)
        
        N1 = a / math.sqrt(1 - e2 * math.sin(phi1)**2)
        R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1)**2)**1.5
        D = (este - FE) / (N1 * k0)
        
        lat = phi1 - (N1 * math.tan(phi1) / R1) * (D**2/2 - (5 + 3*math.tan(phi1)**2)*D**4/24)
        lon = lon0 + (D - (1 + 2*math.tan(phi1)**2)*D**3/6) / math.cos(phi1)
        
        return lat * 180.0 / math.pi, lon * 180.0 / math.pi
    except:
        return None, None

@st.cache_data
def cargar_datos_eco(file_source):
    try:
        # Soporte Excel/CSV
        if hasattr(file_source, 'name') and file_source.name.endswith('.xlsx'):
            df = pd.read_excel(file_source)
        elif str(file_source).endswith('.xlsx'):
            df = pd.read_excel(file_source)
        else:
            df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        
        # Limpieza de columnas
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_name = next((c for c in df.columns if 'CLUSTER' in c), None)
        c_este = next((c for c in df.columns if 'ESTE' in c), None)
        c_norte = next((c for c in df.columns if 'NORTE' in c), None)

        if not all([c_name, c_este, c_norte]):
            st.error(f"Faltan columnas. Detectadas: {list(df.columns)}")
            return pd.DataFrame()

        df_f = df[[c_name, c_este, c_norte]].copy()
        df_f.columns = ['NAME', 'E', 'N']
        
        # Limpiar números
        for c in ['E', 'N']:
            df_f[c] = pd.to_numeric(df_f[c].astype(str).str.replace(r'[^0-9.]', '', regex=True), errors='coerce')
        
        df_f = df_f.dropna()
        
        # --- APLICAR LA CONVERSIÓN CALIBRADA (Este-Este) ---
        res = df_f.apply(lambda r: proyectadas_a_latlon_esteeste(r['E'], r['N']), axis=1)
        df_f['lat'] = [r[0] for r in res]
        df_f['lon'] = [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
file = st.sidebar.file_uploader("Cargar Coordenadas:", type=["csv", "xlsx"])
path_repo = "COORDENADAS_GOR.xlsx"

df = pd.DataFrame()
if file: df = cargar_datos_eco(file)
elif os.path.exists(path_repo): df = cargar_datos_eco(path_repo)

puntos = []
if not df.empty:
    st.sidebar.success(f"✅ Motor Este-Este Activo")
    busqueda = st.sidebar.text_area("Ruta de Trabajo (ej: CASE0015):", "CASE0015")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    
    for i, n in enumerate(nombres_in):
        k = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df[df['KEY'] == k]
        if not match.empty:
            puntos.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon'], 'color': 'red'})

# --- MAPA SATELITAL DE ALTA PRECISIÓN ---
# Centro inicial en Rubiales
centro = [puntos[0]['lat'], puntos[0]['lon']] if puntos else [3.991, -71.732]
m = folium.Map(location=centro, zoom_start=17) # Zoom muy alto para ver la locación

# Capa Satelital de Google (Híbrida: Satélite + Etiquetas)
folium.TileLayer(
    tiles = 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    attr = 'Google Maps Satellite',
    name = 'Vista Satélite',
    overlay = False,
    control = True
).add_to(m)

for p in puntos:
    # Marcador principal (más pequeño y elegante)
    folium.CircleMarker(
        location=[p['lat'], p['lon']],
        radius=5,
        color='red',
        fill=True,
        fill_color='white',
        fill_opacity=0.9,
        tooltip=p['n']
    ).add_to(m)
    
    # Etiqueta de texto (pequeña y sin fondo blanco para no tapar)
    folium.map.Marker(
        [p['lat'], p['lon']],
        icon=DivIcon(
            icon_size=(100,20),
            icon_anchor=(-10, 10),
            html=f'<div style="font-size: 8pt; color: #ffcccc; font-weight: bold; text-shadow: 1px 1px 2px black;">{p["n"]}</div>'
        )
    ).add_to(m)

# Forzar redibujado con key único
st_folium(m, width=1100, height=600, key="mapa_precision_v40")
