import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
from folium.features import DivIcon

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="LOGÍSTICA RUBIALES V6.6", layout="wide", page_icon="🦎")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .tramo-card {
        margin-bottom: 12px; 
        padding: 14px; 
        background: #161b22; 
        border-radius: 10px; 
        border-left: 6px solid; 
        border-right: 1px solid #30363d;
    }
    .tramo-nombres { color: #ffffff; font-size: 0.95rem; font-weight: 600; }
    .tramo-distancia { font-size: 1.25rem; font-weight: 800; display: block; }
</style>
""", unsafe_allow_html=True)

# --- MOTOR DE COORDENADAS ---
def proyectadas_a_latlon_colombia(este, norte):
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        # Origen Nacional (E > 4M) o Central
        if este > 4000000:
            lat0_deg, lon0_deg, k0, FE, FN = (4.0, -73.0, 0.9992, 5000000.0, 2000000.0)
        else:
            lat0_deg, lon0_deg, k0, FE, FN = (4.596200417, -71.077507917, 1.0, 1000000.0, 1000000.0)
        
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

def obtener_ruta_mejorada(p1, p2):
    # Usamos overview=full y steps=false para obtener la geometría máxima
    # El parámetro overview=full es vital para no perder detalle en curvas
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=5).json()
        if r['code'] == 'Ok':
            coords = [[lat, lon] for lon, lat in r['routes'][0]['geometry']['coordinates']]
            distancia = r['routes'][0]['distance'] / 1000
            
            # --- CORRECCIÓN DE "LLEGADA AL POZO" ---
            # Si el último punto de la ruta está a más de 50 metros del pozo real,
            # forzamos una conexión directa para que no quede "a mitad de camino"
            final_coord = [p2['lat'], p2['lon']]
            if coords[-1] != final_coord:
                coords.append(final_coord)
            
            return coords, distancia
    except: pass
    return None, 0

@st.cache_data
def cargar_maestro(file):
    try:
        df = pd.read_excel(file) if file.name.endswith('.xlsx') else pd.read_csv(file, encoding='latin-1', sep=None, engine='python')
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_n = next(c for c in df.columns if any(k in c for k in ['POZO', 'NAME', 'CLUSTER']))
        c_e, c_nt = next(c for c in df.columns if 'ESTE' in c), next(c for c in df.columns if 'NORTE' in c)
        df_f = df[[c_n, c_e, c_nt]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        coords = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [c[0] for c in coords], [c[1] for c in coords]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        return df_f.dropna(subset=['lat'])
    except: return pd.DataFrame()

# --- INTERFAZ ---
st.markdown("<h1 style='text-align: center;'>🦎 LOGÍSTICA DE ACCESO - RUBIALES / CAÑO SUR</h1>", unsafe_allow_html=True)

maestro = st.file_uploader("📂 Cargar Coordenadas Maestro:", type=["xlsx", "csv"])

if maestro:
    db = cargar_maestro(maestro)
    col_ctrl, col_map = st.columns([1, 2.5])
    
    with col_ctrl:
        txt_input = st.text_area("Orden de Pozos:", placeholder="Ej: CASE0092\nCASE0100", height=150)
        nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]
        
        puntos_validos = []
        for i, n in enumerate(nombres):
            key = re.sub(r'[^a-zA-Z0-9]', '', n)
            match = db[db['KEY'].str.contains(key, case=False, na=False)]
            if not match.empty:
                row = match.iloc[0]
                puntos_validos.append({'id': i+1, 'n': row['NAME'], 'lat': row['lat'], 'lon': row['lon']})

        if len(puntos_validos) >= 2:
            total_km = 0
            colores = ["#00FFCC", "#FF007F", "#FFD700", "#00BFFF"]
            
            for i in range(len(puntos_validos)-1):
                p1, p2 = puntos_validos[i], puntos_validos[i+1]
                _, km = obtener_ruta_mejorada(p1, p2)
                total_km += km
                c = colores[i % len(colores)]
                st.markdown(f"""
                <div class="tramo-card" style="border-left-color: {c};">
                    <div style="color: #8b949e; font-size: 0.7rem;">TRAMO {i+1} ➔ {i+2}</div>
                    <div class="tramo-nombres">{p1['n']} <span style="color:{c}">➔</span> {p2['n']}</div>
                    <span class="tramo-distancia" style="color:{c};">{km:.2f} KM</span>
                </div>
                """, unsafe_allow_html=True)
            st.metric("DISTANCIA TOTAL ESTIMADA", f"{total_km:.2f} KM")

    with col_map:
        if len(puntos_validos) >= 2:
            m = folium.Map(location=[puntos_validos[0]['lat'], puntos_validos[0]['lon']], zoom_start=14, tiles=None)
            folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Híbrido').add_to(m)
            
            for i in range(len(puntos_validos)-1):
                geom, _ = obtener_ruta_mejorada(puntos_validos[i], puntos_validos[i+1])
                if geom:
                    c = colores[i % len(colores)]
                    # Ruta principal
                    folium.PolyLine(geom, color=c, weight=4, opacity=0.8).add_to(m)
            
            for p in puntos_validos:
                color_p = colores[(p['id']-1) % len(colores)]
                html = f"""<div style="background:{color_p}; color:black; border-radius:50%; width:22px; height:22px; line-height:22px; text-align:center; font-weight:bold; border:2px solid white;">{p['id']}</div>"""
                folium.Marker([p['lat'], p['lon']], icon=DivIcon(html=html, icon_anchor=(11,11)), tooltip=p['n']).add_to(m)
            
            st_folium(m, width="100%", height=700)
