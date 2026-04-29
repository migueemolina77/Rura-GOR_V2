import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon
from geopy.distance import geodesic # Necesitarás añadir 'geopy' a requirements.txt

st.set_page_config(page_title="Logística Rubiales v4.5", layout="wide")
st.title("🚜 Planificador Logístico: Cálculo de Rutas")

# --- MOTOR DE GEORREFERENCIACIÓN ---
def proyectadas_a_latlon_colombia(este, norte):
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
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
    except: return None, None

@st.cache_data
def cargar_datos_eco(file_source):
    try:
        if hasattr(file_source, 'name') and file_source.name.endswith('.xlsx'): df = pd.read_excel(file_source)
        else: df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_name = next((c for c in df.columns if any(k in c for k in ['CLUSTER', 'POZO', 'NAME', 'PAD'])), None)
        c_este = next((c for c in df.columns if 'ESTE' in c or 'COORDX' in c), None)
        c_norte = next((c for c in df.columns if 'NORTE' in c or 'COORDY' in c), None)
        df_f = df[[c_name, c_este, c_norte]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        for c in ['E', 'N']: df_f[c] = pd.to_numeric(df_f[c].astype(str).str.replace(r'[^0-9.]', '', regex=True), errors='coerce')
        res = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [r[0] for r in res], [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        return df_f.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except: return pd.DataFrame()

# --- LÓGICA DE CARGA ---
file = st.sidebar.file_uploader("Cargar Coordenadas:", type=["csv", "xlsx"])
df = cargar_datos_eco(file) if file else cargar_datos_eco("COORDENADAS_GOR.xlsx") if os.path.exists("COORDENADAS_GOR.xlsx") else pd.DataFrame()

puntos_ruta = []
distancia_total = 0.0

if not df.empty:
    st.sidebar.success("📍 Coordenadas Calibradas")
    busqueda = st.sidebar.text_area("Ingresa Clústeres (Orden de Ruta):", "CLUSTER - 33-II\nCLUSTER - 34")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    
    for i, n in enumerate(nombres_in):
        match = df[df['KEY'] == re.sub(r'[^a-zA-Z0-9]', '', n)]
        if not match.empty:
            puntos_ruta.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})

    # Calcular distancia entre puntos consecutivos
    if len(puntos_ruta) > 1:
        for i in range(len(puntos_ruta) - 1):
            p1 = (puntos_ruta[i]['lat'], puntos_ruta[i]['lon'])
            p2 = (puntos_ruta[i+1]['lat'], puntos_ruta[i+1]['lon'])
            distancia_total += geodesic(p1, p2).kilometers

# --- INTERFAZ DE RESULTADOS ---
if puntos_ruta:
    col1, col2 = st.columns([3, 1])
    with col2:
        st.metric("Distancia Total", f"{distancia_total:.2f} km")
        st.write("**Resumen de paradas:**")
        for p in puntos_ruta:
            st.write(f"{p['id']}. {p['n']}")

# --- MAPA ---
avg_lat = sum(p['lat'] for p in puntos_ruta) / len(puntos_ruta) if puntos_ruta else 3.991
avg_lon = sum(p['lon'] for p in puntos_ruta) / len(puntos_ruta) if puntos_ruta else -71.732

m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13, tiles=None)
folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google Satellite Hybrid', name='Vista Logística').add_to(m)

# Trazar línea de ruta
if len(puntos_ruta) > 1:
    coords_linea = [[p['lat'], p['lon']] for p in puntos_ruta]
    folium.PolyLine(coords_linea, color="yellow", weight=4, opacity=0.8, dash_array='10').add_to(m)

for p in puntos_ruta:
    folium.CircleMarker([p['lat'], p['lon']], radius=6, color='yellow', fill=True, fill_color='red', fill_opacity=1).add_to(m)
    folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(icon_size=(150,20), icon_anchor=(-15, 10),
        html=f'<div style="font-size: 10pt; color: white; font-weight: bold; background: rgba(0,0,0,0.6); padding: 2px 6px; border-radius: 4px; border: 1px solid yellow;">{p["id"]}. {p["n"]}</div>')).add_to(m)

st_folium(m, width=1100, height=550, key="mapa_v45")
