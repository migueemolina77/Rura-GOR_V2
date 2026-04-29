import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
import os
from folium.features import DivIcon

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Logística Rubiales v4.8", layout="wide")
st.title("🚜 Planificador Logístico: Rutas y Kilometraje Real")

# --- 1. MOTOR DE CONVERSIÓN DE COORDENADAS ---
def proyectadas_a_latlon_colombia(este, norte):
    """Convierte coordenadas Magna-SIRGAS a Lat/Lon"""
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        # Determinación de origen (Origen Nacional vs Central)
        if este > 4000000:
            lat0_deg, lon0_deg, k0, FE, FN = 4.0, -73.0, 0.9992, 5000000.0, 2000000.0
        else:
            lat0_deg, lon0_deg, k0, FE, FN = 4.596200417, -71.077507917, 1.0, 1000000.0, 1000000.0
        
        lat0, lon0 = math.radians(lat0_deg), math.radians(lon0_deg)
        M0 = a * ((1 - e2/4 - 3*e2**2/64)*lat0 - (3*e2/8 + 3*e2**2/32)*math.sin(2*lat0) + (15*e2**2/256)*math.sin(4*lat0))
        M = M0 + (norte - FN) / k0
        mu = M / (a * (1 - e2/4 - 3*e2**2/64))
        e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
        phi1 = mu + (3*e1/2 - 27*e1**3/32)*math.sin(2*mu) + (21*e1**2/16 - 55*e1**4/32)*math.sin(4*mu)
        N1 = a / math.sqrt(1 - e2 * math.sin(phi1)**2)
        R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1)**2)**1.5
        D = (este - FE) / (N1 * k0)
        lat = phi1 - (N1 * math.tan(phi1) / R1) * (D**2/2 - (5 + 3*math.tan(phi1)**2)*D**4/24)
        lon = lon0 + (D - (1 + 2*math.tan(phi1)**2)*D**3/6) / math.cos(phi1)
        return math.degrees(lat), math.degrees(lon)
    except:
        return None, None

# --- 2. MOTOR DE RUTAS VIALES (OSRM) ---
def obtener_ruta_vial(puntos):
    if len(puntos) < 2: return None, 0
    coords_str = ";".join([f"{p['lon']},{p['lat']}" for p in puntos])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=5)
        res = r.json()
        if res['code'] == 'Ok':
            geometria = res['routes'][0]['geometry']['coordinates']
            ruta_folium = [[lat, lon] for lon, lat in geometria]
            distancia_km = res['routes'][0]['distance'] / 1000
            return ruta_folium, distancia_km
    except:
        return None, 0
    return None, 0

# --- 3. PROCESAMIENTO DE ARCHIVOS ---
@st.cache_data
def cargar_y_procesar_datos(file_source):
    try:
        if hasattr(file_source, 'name') and file_source.name.endswith('.xlsx'):
            df = pd.read_excel(file_source)
        else:
            df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        
        # Limpiar nombres de columnas
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_name = next((c for c in df.columns if any(k in c for k in ['CLUSTER', 'POZO', 'NAME', 'PAD', 'ELEMENTO'])), None)
        c_este = next((c for c in df.columns if 'ESTE' in c or 'COORDX' in c), None)
        c_norte = next((c for c in df.columns if 'NORTE' in c or 'COORDY' in c), None)
        
        df_f = df[[c_name, c_este, c_norte]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        
        # Convertir a Lat/Lon
        res = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [r[0] for r in res], [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except Exception as e:
        st.error(f"Error al procesar el archivo: {e}")
        return pd.DataFrame()

# --- 4. INTERFAZ Y LÓGICA PRINCIPAL ---
st.sidebar.header("Configuración de Carga")
file = st.sidebar.file_uploader("Cargar Coordenadas (Excel/CSV):", type=["csv", "xlsx"])

# Inicialización de la ruta
puntos_ruta = []

# Cargar datos
if file:
    df_db = cargar_y_procesar_datos(file)
elif os.path.exists("COORDENADAS_GOR.xlsx"):
    df_db = cargar_y_procesar_datos("COORDENADAS_GOR.xlsx")
else:
    df_db = pd.DataFrame()

if not df_db.empty:
    st.sidebar.success("✅ Base de Datos Cargada")
    busqueda = st.sidebar.text_area("Ruta de Trabajo (Ingresa nombres):", "CLUSTER - 33-II\nCLUSTER - 34")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    
    for i, n in enumerate(nombres_in):
        key_busqueda = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_db[df_db['KEY'].str.contains(key_busqueda, case=False, na=False)]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'n': match.iloc[0]['NAME'], 
                'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']
            })

# --- 5. VISUALIZACIÓN ---
if len(puntos_ruta) >= 2:
    geometria_vial, km_reales = obtener_ruta_vial(puntos_ruta)
    
    col1, col2 = st.columns([3, 1])
    with col2:
        st.metric("Distancia por Vía", f"{km_reales:.2f} km")
        st.write("**Paradas confirmadas:**")
        for p in puntos_ruta:
            st.write(f"{p['id']}. {p['n']}")
    
    with col1:
        m = folium.Map(location=[puntos_ruta[0]['lat'], puntos_ruta[0]['lon']], zoom_start=14, tiles=None)
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', 
            attr='Google Satellite Hybrid', name='Vista Satelital'
        ).add_to(m)

        if geometria_vial:
            folium.PolyLine(geometria_vial, color="#00FFCC", weight=6, opacity=0.8).add_to(m)

        for p in puntos_ruta:
            folium.CircleMarker([p['lat'], p['lon']], radius=7, color='white', fill=True, fill_color='red').add_to(m)
            folium.map.Marker(
                [p['lat'], p['lon']], 
                icon=DivIcon(html=f'<div style="font-size: 10pt; color: white; font-weight: bold; background: rgba(0,0,0,0.6); padding: 2px 5px; border-radius: 3px; border: 1px solid white;">{p["n"]}</div>')
            ).add_to(m)

        st_folium(m, width="100%", height=600)
else:
    st.info("👋 Por favor ingresa al menos dos puntos válidos en el panel izquierdo para calcular la ruta.")
