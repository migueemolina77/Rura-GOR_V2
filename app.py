import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
from pyproj import Transformer
import os

# 1. Configuración de página
st.set_page_config(page_title="Logística Rubiales v2 - Origen Nacional", layout="wide")

# 2. Conversión de Coordenadas (EPSG:9377 a WGS84)
def proyectadas_a_latlon(este, norte):
    try:
        # Definir transformador: Origen Nacional Colombia (9377) -> Lat/Lon (4326)
        # always_xy=True asegura que el orden sea (Este, Norte) -> (Lon, Lat)
        transformer = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(este, norte)
        return lat, lon
    except Exception:
        return None, None

# 3. Carga de datos con validación profunda
@st.cache_data
def cargar_base_coordenadas(file_path):
    if not os.path.exists(file_path):
        st.error(f"⚠️ No se encontró el archivo: {file_path}")
        return None
    
    try:
        # Intentar leer con diferentes encodings (Excel suele usar latin-1 en CSVs)
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='latin-1')

        # Verificar que el archivo tenga datos
        if df.empty:
            st.warning("El archivo de coordenadas está vacío.")
            return None

        # Mapeo según tu nueva estructura: 1: CLUSTER, 2: POZO, 3: ESTE, 4: NORTE
        # Usamos nombres de columnas directamente si existen, sino por índice
        if 'CLUSTER' in df.columns:
            df_coords = df[['CLUSTER', 'POZO', 'ESTE', 'NORTE']].copy()
            df_coords.columns = ['cluster', 'pozo', 'este', 'norte']
        else:
            df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
            df_coords.columns = ['cluster', 'pozo', 'este', 'norte']
        
        # Limpieza numérica
        df_coords['este'] = pd.to_numeric(df_coords['este'], errors='coerce')
        df_coords['norte'] = pd.to_numeric(df_coords['norte'], errors='coerce')
        df_coords = df_coords.dropna(subset=['este', 'norte'])
        
        # Transformación a Lat/Lon
        df_coords[['lat_dec', 'lon_dec']] = df_coords.apply(
            lambda row: proyectadas_a_latlon(row['este'], row['norte']), 
            axis=1, result_type='expand'
        )
        
        # Agrupar por Clúster
        df_final = df_coords.dropna(subset=['lat_dec']).groupby('cluster').agg({
            'lat_dec': 'first', 
            'lon_dec': 'first', 
            'este': 'first',
            'norte': 'first',
            'pozo': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
        
        return df_final
    except Exception as e:
        st.error(f"❌ Error crítico al procesar el CSV: {e}")
        return None

# --- LÓGICA DE LA INTERFAZ ---

st.title("🚜 Plan Logístico Rubiales v2.0")
st.caption("Cálculo de rutas con coordenadas Origen Nacional (EPSG:9377)")

# Carga de la base
archivo_coords = "COORDENADAS_GOR.xlsx - data.csv"
df_maestro = cargar_base_coordenadas(archivo_coords)

if df_maestro is not None:
    # Sidebar
    st.sidebar.header("Orden de Movilización")
    ruta_input = st.sidebar.text_area("Pega los Clústeres (uno por línea):", placeholder="AGRIO-1\nCASE0015")
    nombres_ruta = [n.strip().upper() for n in re.split(r'[\n,]+', ruta_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres_ruta):
        # Filtro seguro
        match = df_maestro[df_maestro['cluster'].astype(str).str.upper() == nombre]
        
        if not match.empty:
            puntos_ruta.append({
                'orden': i + 1,
                'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec'], 
                'pozos': match.iloc[0]['pozo'],
                'este': match.iloc[0]['este'],
                'norte': match.iloc[0]['norte']
            })
        else:
            if nombre: st.sidebar.warning(f"No se encontró: {nombre}")

    # Configuración del Mapa
    centro_lat = df_maestro['lat_dec'].mean()
    centro_lon = df_maestro['lon_dec'].mean()
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=12)

    if len(puntos_ruta) >= 2:
        total_km = 0
        resumen_ruta = []
        for i in range(len(puntos_ruta) - 1):
            p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
            # OSRM para tramos reales
            url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
            try:
                r = requests.get(url, timeout=5).json()
                if r['code'] == 'Ok':
                    geom = [[c[1], c[0]] for c in r['routes'][0]['geometry']['coordinates']]
                    km = r['routes'][0]['distance'] / 1000
                    folium.PolyLine(geom, color="blue", weight=5, opacity=0.7).add_to(m)
                    total_km += km
                    resumen_ruta.append({"Tramo": f"{p1['nombre']} ➔ {p2['nombre']}", "KM": round(km, 2)})
            except: pass
        
        st.sidebar.table(resumen_ruta)
        st.sidebar.metric("Distancia Total", f"{total_km:.2f} Km")

    # Marcadores
    for p in puntos_ruta:
        folium.Marker(
            [p['lat'], p['lon']],
            popup=f"ID: {p['nombre']}<br>Pozos: {p['pozos']}",
            icon=folium.Icon(color='darkblue', icon='industry', prefix='fa')
        ).add_to(m)
        
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(icon_size=(30,30), icon_anchor=(15,15),
            html=f'<div style="font-size: 10pt; color: white; background: black; border-radius: 50%; text-align: center; border: 2px solid white;">{p["orden"]}</div>')
        ).add_to(m)

    st_folium(m, width=1000, height=600)
else:
    st.info("Esperando carga correcta del archivo de coordenadas para habilitar el mapa.")
