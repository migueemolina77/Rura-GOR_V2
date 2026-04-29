import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
import os
from folium.features import DivIcon

# --- CONFIGURACIÓN ESTÉTICA ---
st.set_page_config(page_title="LOGÍSTICA RUBIALES V7.3", layout="wide", page_icon="🦎")

# Estilo CSS - Manteniendo la estética "Reloj Suizo" con los nuevos íconos profesionales
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    h1 { color: #ffffff; font-family: 'Segoe UI', sans-serif; font-weight: 800; letter-spacing: -1px; margin-bottom: 0px; }
    
    /* Tarjetas de tramo estilizadas */
    .tramo-card {
        margin-bottom: 12px; padding: 15px; background: #161b22; 
        border-radius: 10px; border-left: 6px solid; border: 1px solid #30363d;
    }
    .tramo-header { color: #8b949e; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; margin-bottom: 4px; }
    .tramo-nombres { color: #ffffff; font-size: 1rem; font-weight: 600; }
    .tramo-distancia { font-size: 1.3rem; font-weight: 800; margin-top: 5px; display: block; }
    
    /* Alertas Operativas */
    .alerta-box {
        padding: 8px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; margin-top: 8px;
        display: flex; align-items: center; gap: 6px;
    }
    .alerta-despine { background: rgba(255, 75, 75, 0.1); color: #ff4b4b; border: 1px solid #ff4b4b; }
    .alerta-comunidad { background: rgba(255, 184, 0, 0.1); color: #ffb800; border: 1px solid #ffb800; }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
""", unsafe_allow_html=True)

# --- COORDENADAS DE REFERENCIA (COMUNIDADES) ---
COMUNIDADES = {
    "EL OASIS": {"lat": 3.966, "lon": -71.896},
    "RUBIALITOS": {"lat": 3.912, "lon": -72.035}
}

# --- FUNCIONES TÉCNICAS (Motor Magna-SIRGAS ➔ OSRM ➔ WGS84) ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def proyectadas_a_latlon_colombia(este, norte):
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        # Determinación de Origen (Nacional vs Central)
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
    # Solicitamos la ruta con máxima precisión (continue_straight para evitar desvíos innecesarios)
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson&continue_straight=true"
    try:
        r = requests.get(url, timeout=5).json()
        if r['code'] == 'Ok':
            coords = [[lat, lon] for lon, lat in r['routes'][0]['geometry']['coordinates']]
            distancia = r['routes'][0]['distance'] / 1000
            # Forzado de conectividad final para garantizar llegada exacta
            coords.append([p2['lat'], p2['lon']])
            return coords, distancia
    except: pass
    return [[p1['lat'], p1['lon']], [p2['lat'], p2['lon']]], 0

@st.cache_data
def cargar_db(file_source):
    try:
        # Detectar tipo de archivo y cargar
        if isinstance(file_source, str):
            if not os.path.exists(file_source): return pd.DataFrame()
            df = pd.read_excel(file_source)
        else:
            if file_source.name.endswith('.xlsx'):
                df = pd.read_excel(file_source)
            else:
                df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        
        # Limpieza estándar de columnas
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        
        # Identificar columnas críticas (Nombre, Este, Norte)
        c_n = next(c for c in df.columns if any(k in c for k in ['POZO', 'NAME', 'CLUSTER', 'PAD']))
        c_e = next(c for c in df.columns if 'ESTE' in c or 'COORDX' in c)
        c_nt = next(c for c in df.columns if 'NORTE' in c or 'COORDY' in c)
        
        # Filtrar y renombrar
        df_f = df[[c_n, c_e, c_nt]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        
        # Conversión Magna-SIRGAS a WGS84
        coords = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [c[0] for c in coords], [c[1] for c in coords]
        
        # Clave de búsqueda limpia
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat'])
    except:
        return pd.DataFrame()

# --- TÍTULOS Y CABEZOTE ACORDADO (🦎 MAPA GOR - ECOPETROL) ---
st.markdown("<h1 style='text-align: center;'>🦎 MAPA GOR - ECOPETROL</h1>", unsafe_allow_html=True)
st.divider()

# --- FLUJO DE CARGA ---
maestro = st.file_uploader("📂 Por favor, cargue el archivo maestro de coordenadas:", type=["xlsx", "csv"], label_visibility="collapsed")

# Inicialización segura
db = pd.DataFrame()
if maestro:
    db = cargar_db(maestro)
elif os.path.exists("COORDENADAS_GOR.xlsx"):
    # Carga automática si el archivo local existe para agilizar pruebas
    db = cargar_db("COORDENADAS_GOR.xlsx")

if db.empty:
    st.info("👋 **Bienvenido, Miguel.** Por favor, carga el archivo maestro para iniciar la planificación operativa.")
else:
    # --- COLUMNAS PRINCIPALES (1.1 ui, 3 map) ---
    col_ui, col_map = st.columns([1.1, 3])
    
    with col_ui:
        st.subheader("Plan de Ruta")
        entrada = st.text_area("Lista de Pozos:", placeholder="Ej: CLUSTER-34\nCASE0092", height=150)
        nombres = [n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]
        
        puntos_validos = []
        for i, n in enumerate(nombres):
            key = re.sub(r'[^a-zA-Z0-9]', '', n)
            match = db[db['KEY'].str.contains(key, case=False, na=False)]
            if not match.empty:
                row = match.iloc[0]
                puntos_validos.append({'id': i+1, 'n': row['NAME'], 'lat': row['lat'], 'lon': row['lon']})

        if len(puntos_validos) >= 2:
            st.divider()
            km_totales = 0
            all_coords = []
            colores = ["#00FFCC", "#FF007F", "#FFD700", "#00BFFF", "#7CFC00"]
            
            for i in range(len(puntos_validos)-1):
                p_orig, p_dest = puntos_validos[i], puntos_validos[i+1]
                geom, km = obtener_ruta_forzada(p_orig, p_dest)
                km_totales += km
                all_coords.extend(geom)
                c = colores[i % len(colores)]
                
                # Motor de Alertas (Haversine 3km)
                alerta_html = ""
                # Comunidades
                for com, coord in COMUNIDADES.items():
                    if any(haversine(g[0], g[1], coord['lat'], coord['lon']) < 3.0 for g in geom):
                        alerta_html += f'<div class="alerta-box alerta-comunidad"><i class="fa-solid fa-people-group"></i> PASO POR {com}</div>'
                
                # Despine (>30km)
                if km > 30:
                    alerta_html += '<div class="alerta-box alerta-despine"><i class="fa-solid fa-tower-broadcast"></i> DESPINAR TORRE (>30 KM)</div>'
                
                # Tarjetas de Tramo (Estilo Reloj Suizo)
                st.markdown(f"""
                <div class="tramo-card" style="border-left-color: {c};">
                    <div class="tramo-header">Tramo {i+1} ➔ {i+2}</div>
                    <div class="tramo-nombres"><b>{p_orig['n']}</b> ➔ <b>{p_dest['n']}</b></div>
                    <span class="tramo-distancia" style="color:{c};">{km:.2f} KM</span>
                    {alerta_html}
                </div>""", unsafe_allow_html=True)
            
            st.metric("DISTANCIA TOTAL ESTIMADA", f"{km_totales:.2f} KM")

    with col_map:
        if len(puntos_validos) >= 2:
            # Crear mapa adaptativo (tiles satelitales Google)
            m = folium.Map(tiles=None)
            folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite Híbrido').add_to(m)
            
            # Dibujar Rutas con Transparencia y Brillo
            for i in range(len(puntos_validos)-1):
                geom, _ = obtener_ruta_forzada(puntos_validos[i], puntos_validos[i+1])
                c = colores[i % len(colores)]
                # Efecto "Glow" blanco abajo, color neón arriba
                folium.PolyLine(geom, color='white', weight=8, opacity=0.15).add_to(m)
                folium.PolyLine(geom, color=c, weight=5, opacity=0.7).add_to(m)
            
            # --- MARCACIONES PROFESIONALES DE POZO (RESTYLING) ---
            # Icono del machín/torre profesional con FontAwesome (`fa-oil-well`)
            for p in puntos_validos:
                c = colores[(p['id']-1) % len(colores)]
                # Etiqueta compacta y técnica:
                # El ícono fa-oil-well es el símbolo estándar y profesional para un pozo de producción
                label_html = f"""
                <div style="text-align: center;">
                    <div style="background:{c}; color:black; border-radius:50%; width:24px; height:24px; line-height:24px; font-weight:bold; border:2px solid white; font-size:10pt;">{p['id']}</div>
                    <div style="background:rgba(14, 17, 23, 0.9); color:white; padding:3px 8px; border-radius:5px; font-size:9pt; margin-top:4px; border:1px solid {c}; white-space:nowrap; box-shadow: 2px 2px 5px rgba(0,0,0,0.5);">
                        <i class="fa-solid fa-oil-well" style="color:{c}; margin-right:4px;"></i>{p['n']}
                    </div>
                </div>"""
                
                folium.Marker([p['lat'], p['lon']], icon=DivIcon(html=label_html, icon_anchor=(11, 11))).add_to(m)
            
            # --- AUTO-ENFOQUE DINÁMICO (Solo los puntos buscados) ---
            if all_coords:
                # Calculamos SW (min_lat, min_lon) y NE (max_lat, max_lon)
                sw = [min(p[0] for p in all_coords), min(p[1] for p in all_coords)]
                ne = [max(p[0] for p in all_coords), max(p[1] for p in all_coords)]
                m.fit_bounds([sw, ne])
            
            st_folium(m, width="100%", height=750)
        else:
            st.info("💡 Por favor, ingresa los nombres de los pozos en el cuadro lateral para trazar la logística operativa.")
