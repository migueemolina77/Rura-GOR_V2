import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.9", layout="wide")
st.title("🚜 Precisión Magna-SIRGAS: Logística Rubiales")

# --- MOTOR DE GEORREFERENCIACIÓN MAGNA-SIRGAS (EPSG:9377) ---
def proyectadas_a_latlon_magna(este, norte):
    """
    Conversión de Origen Nacional (9377) a WGS84.
    Parámetros oficiales del IGAC para Colombia.
    """
    try:
        # Constantes del elipsoide GRS80 / WGS84
        a = 6378137.0
        f = 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        ep2 = (a**2 - b**2) / b**2
        
        # Parámetros del Origen Nacional (EPSG:9377)
        lat0 = 4.0 * math.pi / 180.0
        lon0 = -73.0 * math.pi / 180.0
        k0 = 0.9992
        FE = 5000000.0
        FN = 2000000.0
        
        # Cálculos de proyección inversa
        M0 = a * ((1 - e2/4 - 3*e2**2/64 - 5*e2**3/256)*lat0 - (3*e2/8 + 3*e2**2/32 + 45*e2**3/1024)*math.sin(2*lat0) + (15*e2**2/256 + 45*e2**3/1024)*math.sin(4*lat0) - (35*e2**3/3072)*math.sin(6*lat0))
        M = M0 + (norte - FN) / k0
        
        mu = M / (a * (1 - e2/4 - 3*e2**2/64 - 5*e2**3/256))
        e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
        
        phi1 = mu + (3*e1/2 - 27*e1**3/32)*math.sin(2*mu) + (21*e1**2/16 - 55*e1**4/32)*math.sin(4*mu) + (151*e1**3/96)*math.sin(6*mu)
        
        N1 = a / math.sqrt(1 - e2 * math.sin(phi1)**2)
        R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1)**2)**1.5
        D = (este - FE) / (N1 * k0)
        
        lat = phi1 - (N1 * math.tan(phi1) / R1) * (D**2/2 - (5 + 3*math.tan(phi1)**2 + 10*math.tan(phi1)**2 - 4*math.tan(phi1)**4 - 9*ep2)*D**4/24)
        lon = lon0 + (D - (1 + 2*math.tan(phi1)**2 + ep2)*D**3/6 + (5 - 2*math.tan(phi1)**2 + 28*math.tan(phi1)**2 - 3*ep2**2 + 8*math.tan(phi1)**4 + 24*math.tan(phi1)**4)*D**5/120) / math.cos(phi1)
        
        return lat * 180.0 / math.pi, lon * 180.0 / math.pi
    except:
        return None, None

@st.cache_data
def cargar_datos_eco(file_source):
    try:
        # Detección de Excel o CSV
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

        df_f = df[[c_name, c_este, c_norte]].copy()
        df_f.columns = ['NAME', 'E', 'N']
        
        # Limpiar números
        for c in ['E', 'N']:
            df_f[c] = pd.to_numeric(df_f[c].astype(str).str.replace(r'[^0-9.]', '', regex=True), errors='coerce')
        
        df_f = df_f.dropna()
        
        # Aplicar conversión Magna-SIRGAS
        res = df_f.apply(lambda r: proyectadas_a_latlon_magna(r['E'], r['N']), axis=1)
        df_f['lat'] = [r[0] for r in res]
        df_f['lon'] = [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
file = st.sidebar.file_uploader("Cargar Coordenadas (Excel/CSV):", type=["csv", "xlsx"])
path_repo = "COORDENADAS_GOR.xlsx"

df = pd.DataFrame()
if file: df = cargar_datos_eco(file)
elif os.path.exists(path_repo): df = cargar_datos_eco(path_repo)

puntos = []
if not df.empty:
    st.sidebar.success(f"Sistema Magna-SIRGAS Activo")
    busqueda = st.sidebar.text_area("Ruta de Trabajo:", "")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    
    for i, n in enumerate(nombres_in):
        k = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df[df['KEY'] == k]
        if not match.empty:
            puntos.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon'], 'color': 'red'})
    
    # Si no hay búsqueda, mostrar los primeros para validar centrado
    if not puntos:
        for i, row in df.head(8).iterrows():
            puntos.append({'id': '•', 'n': row['NAME'], 'lat': row['lat'], 'lon': row['lon'], 'color': 'blue'})

# --- MAPA CON CAPA SATELITAL ---
c_lat, c_lon = (puntos[0]['lat'], puntos[0]['lon']) if puntos else (3.99, -71.73)
m = folium.Map(location=[c_lat, c_lon], zoom_start=13)

# Añadimos vista de Satélite para que veas las locaciones reales
folium.TileLayer(
    tiles = 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    attr = 'Google',
    name = 'Satélite',
    overlay = False,
    control = True
).add_to(m)

for p in puntos:
    folium.Marker([p['lat'], p['lon']], tooltip=p['n'], icon=folium.Icon(color=p['color'])).add_to(m)
    folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(icon_size=(20,20), icon_anchor=(-15,20),
        html=f'<div style="font-size: 8pt; color: white; background: {p["color"]}; border-radius: 4px; padding: 1px 4px; font-weight: bold; border: 1px solid white; white-space: nowrap;">{p["n"]}</div>')).add_to(m)

st_folium(m, width=1100, height=600, key="mapa_magna")
