import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
from folium.features import DivIcon

# --- CONFIGURACIÓN DE PÁGINA Y ESTILO RECUPERADO ---
st.set_page_config(page_title="LOGÍSTICA RUBIALES V6.9", layout="wide", page_icon="🦎")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    /* Estilo para las tarjetas de tramos laterales */
    .tramo-card {
        margin-bottom: 15px; padding: 18px; background: #1c2128; 
        border-radius: 12px; border-left: 8px solid; border: 1px solid #30363d;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .tramo-nombres { color: #adbac7; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;}
    .tramo-puntos { color: #ffffff; font-size: 1.1rem; font-weight: 700; margin-bottom: 8px; display: block;}
    .tramo-distancia { font-size: 1.4rem; font-weight: 900; }
    
    /* Personalización de inputs */
    .stTextArea textarea { background-color: #0d1117 !important; color: #58a6ff !important; border: 1px solid #30363d !important;}
</style>
""", unsafe_allow_html=True)

# --- MOTOR DE COORDENADAS (Magna-SIRGAS) ---
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

def obtener_ruta_forzada(p1, p2):
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson&continue_straight=true"
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
def cargar_db(file):
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

# --- INTERFAZ RECUPERADA ---
st.markdown("<h1 style='text-align: left; color: #ffffff; font-family: sans-serif;'>🚜 LOGÍSTICA RUBIALES</h1>", unsafe_allow_html=True)

archivo = st.file_uploader("Cargar Base de Coordenadas (XLSX/CSV):", label_visibility="collapsed")

if archivo:
    db = cargar_db(archivo)
    col_ui, col_map = st.columns([1, 2.5], gap="medium")
    
    with col_ui:
        st.markdown("### 📍 Orden del Recorrido")
        entrada = st.text_area("Pega los pozos aquí (uno por línea):", height=150, placeholder="CLUSTER-33\nCASE0021...")
        lista_nombres = [n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]
        
        puntos_seleccionados = []
        for i, n in enumerate(lista_nombres):
            key = re.sub(r'[^a-zA-Z0-9]', '', n)
            match = db[db['KEY'].str.contains(key, case=False, na=False)]
            if not match.empty:
                row = match.iloc[0]
                puntos_seleccionados.append({'id': i+1, 'n': row['NAME'], 'lat': row['lat'], 'lon': row['lon']})

        if len(puntos_seleccionados) >= 2:
            st.divider()
            km_totales = 0
            all_coords_for_zoom = []
            colores = ["#00FFCC", "#FF007F", "#FFD700", "#00BFFF", "#7CFC00"]
            
            for i in range(len(puntos_seleccionados)-1):
                geom, km = obtener_ruta_forzada(puntos_seleccionados[i], puntos_seleccionados[i+1])
                km_totales += km
                all_coords_for_zoom.extend(geom)
                c = colores[i % len(colores)]
                
                # Restauración de la tarjeta visual por tramo
                st.markdown(f"""
                <div class="tramo-card" style="border-left-color: {c};">
                    <div class="tramo-nombres">Tramo {i+1}</div>
                    <span class="tramo-puntos">{puntos_seleccionados[i]['n']} ➔ {puntos_seleccionados[i+1]['n']}</span>
                    <span class="tramo-distancia" style="color:{c};">{km:.2f} KM</span>
                </div>""", unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="background: #238636; padding: 15px; border-radius: 10px; text-align: center; margin-top: 20px;">
                <span style="color: white; font-size: 0.9rem; font-weight: bold; text-transform: uppercase;">Distancia Total</span><br>
                <span style="color: white; font-size: 2.2rem; font-weight: 900;">{km_totales:.2f} km</span>
            </div>""", unsafe_allow_html=True)

    with col_map:
        if len(puntos_seleccionados) >= 2:
            m = folium.Map(tiles=None)
            folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite').add_to(m)
            
            for i in range(len(puntos_seleccionados)-1):
                geom, _ = obtener_ruta_forzada(puntos_seleccionados[i], puntos_seleccionados[i+1])
                color_linea = colores[i % len(colores)]
                # Efecto de brillo para la ruta
                folium.PolyLine(geom, color='white', weight=8, opacity=0.2).add_to(m)
                folium.PolyLine(geom, color=color_linea, weight=4, opacity=0.85).add_to(m)
            
            for p in puntos_seleccionados:
                c = colores[(p['id']-1) % len(colores)]
                # Marcadores numéricos profesionales
                lbl = f"""<div style="background:{c}; color:black; border-radius:50%; width:28px; height:28px; line-height:28px; text-align:center; font-weight:bold; border:2px solid white; box-shadow: 0 0 10px rgba(0,0,0,0.5);">{p['id']}</div>"""
                folium.Marker([p['lat'], p['lon']], icon=DivIcon(html=lbl, icon_anchor=(14,14)), tooltip=p['n']).add_to(m)
            
            # EL CORAZÓN DE TU SOLICITUD: Solo ajusta a los puntos de la búsqueda actual
            if all_coords_for_zoom:
                sw = [min(p[0] for p in all_coords_for_zoom), min(p[1] for p in all_coords_for_zoom)]
                ne = [max(p[0] for p in all_coords_for_zoom), max(p[1] for p in all_coords_for_zoom)]
                m.fit_bounds([sw, ne])
            
            st_folium(m, width="100%", height=750)
