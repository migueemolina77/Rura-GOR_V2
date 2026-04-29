import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
from folium.features import DivIcon

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="MAPA GOR - OPERACIONES", layout="wide", page_icon="🦎")

# Estilo CSS - Manteniendo la estética "Reloj Suizo" con nuevas alertas
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    h1 { color: #ffffff; font-family: 'Segoe UI', sans-serif; font-weight: 800; letter-spacing: -1px; }
    
    .tramo-card {
        margin-bottom: 12px; padding: 15px; background: #161b22; 
        border-radius: 10px; border-left: 6px solid; border: 1px solid #30363d;
    }
    .tramo-header { color: #8b949e; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; margin-bottom: 4px; }
    .tramo-nombres { color: #ffffff; font-size: 1rem; font-weight: 600; }
    .tramo-distancia { font-size: 1.3rem; font-weight: 800; margin-top: 5px; display: block; }
    
    /* Estilo para Alertas Operativas */
    .alerta-seguridad {
        padding: 10px; border-radius: 8px; font-size: 0.85rem; margin-top: 10px;
        display: flex; align-items: center; gap: 8px;
    }
    .alerta-distancia { background-color: rgba(255, 75, 75, 0.15); color: #ff4b4b; border: 1px solid #ff4b4b; }
    .alerta-cacerio { background-color: rgba(255, 165, 0, 0.15); color: #ffa500; border: 1px solid #ffa500; }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
""", unsafe_allow_html=True)

# --- COORDENADAS DE REFERENCIA (CACERÍOS) ---
CACERIOS = {
    "EL OASIS": {"lat": 3.966, "lon": -71.896}, # Coordenadas aproximadas para monitoreo
    "RUBIALITOS": {"lat": 3.912, "lon": -72.035}
}

# --- FUNCIONES TÉCNICAS ---
def haversine_dist(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def proyectadas_a_latlon_colombia(este, norte):
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        lat0_deg, lon0_deg, k0, FE, FN = (4.0, -73.0, 0.9992, 5000000.0, 2000000.0) if este > 4000000 else (4.596200417, -71.077507917, 1.0, 1000000.0, 1000000.0)
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
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=5).json()
        if r['code'] == 'Ok':
            coords = [[lat, lon] for lon, lat in r['routes'][0]['geometry']['coordinates']]
            distancia = r['routes'][0]['distance'] / 1000
            coords.append([p2['lat'], p2['lon']])
            return coords, distancia
    except: pass
    return [[p1['lat'], p1['lon']], [p2['lat'], p2['lon']]], 0

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
st.markdown("<h1 style='text-align: center;'>🦎 MAPA GOR - OPERACIONES RUBIALES</h1>", unsafe_allow_html=True)
st.divider()

archivo = st.file_uploader("📂 Cargue el archivo maestro:", type=["xlsx", "csv"], label_visibility="collapsed")

if archivo:
    db = cargar_maestro(archivo)
    col_ui, col_map = st.columns([1.2, 3])
    
    with col_ui:
        st.subheader("Planificación de Pozos")
        entrada = st.text_area("Orden de Pozos:", height=150)
        nombres = [n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]
        
        puntos_validos = []
        for i, n in enumerate(nombres):
            key = re.sub(r'[^a-zA-Z0-9]', '', n)
            match = db[db['KEY'].str.contains(key, case=False, na=False)]
            if not match.empty:
                puntos_validos.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})

        if len(puntos_validos) >= 2:
            st.divider()
            all_coords = []
            colores_hex = ["#00FFCC", "#FF007F", "#FFD700", "#00BFFF", "#7CFC00"]
            
            for i in range(len(puntos_validos)-1):
                p_orig, p_dest = puntos_validos[i], puntos_validos[i+1]
                geom, km = obtener_ruta_mejorada(p_orig, p_dest)
                all_coords.extend(geom)
                c = colores_hex[i % len(colores_hex)]
                
                # Análisis de Alertas
                alerta_html = ""
                # 1. Alerta de Caceríos (si algún punto de la ruta está a menos de 1.5km de un cacerío)
                for cac_nombre, cac_coords in CACERIOS.items():
                    pasa_cerca = any(haversine_dist(g[0], g[1], cac_coords['lat'], cac_coords['lon']) < 1.5 for g in geom)
                    if pasa_cerca:
                        alerta_html += f'<div class="alerta-seguridad alerta-cacerio"><i class="fa-solid fa-house-chimney"></i> PASO POR {cac_nombre}</div>'
                
                # 2. Alerta de Despine
                if km > 30:
                    alerta_html += '<div class="alerta-seguridad alerta-distancia"><i class="fa-solid fa-triangle-exclamation"></i> DESPINAR TORRE (>30 KM)</div>'
                
                st.markdown(f"""
                <div class="tramo-card" style="border-left-color: {c};">
                    <div class="tramo-header">Tramo {i+1} ➔ {i+2}</div>
                    <div class="tramo-nombres"><b>{p_orig['n']}</b> ➔ <b>{p_dest['n']}</b></div>
                    <span class="tramo-distancia" style="color:{c};">{km:.2f} KM</span>
                    {alerta_html}
                </div>""", unsafe_allow_html=True)

    with col_map:
        if len(puntos_validos) >= 2:
            m = folium.Map(tiles=None)
            folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Híbrido').add_to(m)
            
            # Dibujar Rutas
            for i in range(len(puntos_validos)-1):
                geom, _ = obtener_ruta_mejorada(puntos_validos[i], puntos_validos[i+1])
                folium.PolyLine(geom, color=colores_hex[i % len(colores_hex)], weight=5, opacity=0.8).add_to(m)
            
            # Dibujar Caceríos como puntos de advertencia en el mapa
            for cac_nombre, cac_coords in CACERIOS.items():
                folium.CircleMarker([cac_coords['lat'], cac_coords['lon']], radius=15, color='orange', fill=True, popup=cac_nombre).add_to(m)
            
            # Marcadores de Pozos
            for p in puntos_validos:
                c = colores_hex[(p['id']-1) % len(colores_hex)]
                lbl = f'<div style="background:{c}; color:black; border-radius:50%; width:24px; height:24px; line-height:24px; text-align:center; font-weight:bold; border:2px solid white;">{p['id']}</div>'
                folium.Marker([p['lat'], p['lon']], icon=DivIcon(html=lbl, icon_anchor=(12, 12))).add_to(m)
            
            if all_coords:
                m.fit_bounds([[min(p[0] for p in all_coords), min(p[1] for p in all_coords)],
                             [max(p[0] for p in all_coords), max(p[1] for p in all_coords)]])
            
            st_folium(m, width="100%", height=700)
