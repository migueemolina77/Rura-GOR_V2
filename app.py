import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
from pyproj import Transformer

# Configuración de página
st.set_page_config(page_title="Logística Rubiales v2 - CASE", layout="wide")

# --- FUNCIONES DE CONVERSIÓN ---

def proyectadas_a_latlon(este, norte):
    """
    Convierte coordenadas Este/Norte (Origen Nacional EPSG:9377) 
    a Latitud/Longitud (WGS84 EPSG:4326).
    """
    try:
        # Definir el transformador: De Origen Nacional (9377) a WGS84 (4326)
        # Nota: En pyproj 2.0+, la convención es (lat, lon) o (y, x) según el EPSG.
        transformer = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(este, norte)
        return lat, lon
    except Exception as e:
        return None, None

# --- CARGA DE DATOS ---

@st.cache_data
def cargar_base_coordenadas(file_path):
    # Carga directa: El nuevo CSV tiene encabezados en la fila 0
    df = pd.read_csv(file_path, encoding='utf-8')
    
    # Mapeo según el archivo COORDENADAS_GOR:
    # 1: CLUSTER | 2: POZO | 3: ESTE | 4: NORTE
    df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
    df_coords.columns = ['cluster', 'pozo', 'este', 'norte']
    
    # Limpieza de datos numéricos
    df_coords['este'] = pd.to_numeric(df_coords['este'], errors='coerce')
    df_coords['norte'] = pd.to_numeric(df_coords['norte'], errors='coerce')
    
    # Eliminar filas sin coordenadas válidas
    df_coords = df_coords.dropna(subset=['este', 'norte'])
    
    # Aplicar conversión a cada fila
    # Creamos dos nuevas columnas: lat_dec y lon_dec
    df_coords[['lat_dec', 'lon_dec']] = df_coords.apply(
        lambda row: proyectadas_a_latlon(row['este'], row['norte']), 
        axis=1, result_type='expand'
    )
    
    # Agrupamos por Clúster para el itinerario
    df_final = df_coords.dropna(subset=['lat_dec']).groupby('cluster').agg({
        'lat_dec': 'first', 
        'lon_dec': 'first', 
        'este': 'first',
        'norte': 'first',
        'pozo': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    return df_final

# --- LÓGICA DE RUTAS (OSRM) ---

def obtener_tramo_real(punto_a, punto_b):
    url = f"http://router.project-osrm.org/route/v1/driving/{punto_a['lon']},{punto_a['lat']};{punto_b['lon']},{punto_b['lat']}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data['code'] == 'Ok':
            ruta = data['routes'][0]
            geometria = [[coord[1], coord[0]] for coord in ruta['geometry']['coordinates']]
            distancia_km = ruta['distance'] / 1000
            return geometria, distancia_km
    except:
        pass
    return [], 0

# --- INTERFAZ DE USUARIO ---

st.title("🚜 Plan Logístico Rubiales v2.0")
st.markdown("Cálculo de rutas basado en coordenadas **Origen Nacional (EPSG:9377)**")

colores_tramos = ['#E74C3C', '#2ECC71', '#3498DB', '#F1C40F', '#9B59B6', '#E67E22']

try:
    # Carga del nuevo archivo
    df_maestro = cargar_base_coordenadas("COORDENADAS_GOR.xlsx - data.csv")

    st.sidebar.header("Configuración de Ruta")
    ruta_input = st.sidebar.text_area("Pega los Clústeres (uno por línea):", 
                                     placeholder="AGRIO-1\nCASE0015\nCASE0019")
    
    nombres_ruta = [n.strip().upper() for n in re.split(r'[\n,]+', ruta_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres_ruta):
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

    # Mapa base centrado en el promedio de los puntos
    centro_lat = df_maestro['lat_dec'].mean()
    centro_lon = df_maestro['lon_dec'].mean()
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=12)

    if len(puntos_ruta) >= 2:
        resumen_ruta = []
        total_km = 0
        
        for i in range(len(puntos_ruta) - 1):
            p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
            geometria, km = obtener_tramo_real(p1, p2)
            
            if geometria:
                color_asignado = colores_tramos[i % len(colores_tramos)]
                folium.PolyLine(geometria, color=color_asignado, weight=6, opacity=0.8).add_to(m)
                
                total_km += km
                resumen_ruta.append({
                    "Tramo": f"{p1['orden']} ➔ {p2['orden']}",
                    "Origen-Destino": f"{p1['nombre']} a {p2['nombre']}",
                    "KM": round(km, 2)
                })

        st.sidebar.subheader("Itinerario")
        st.sidebar.table(resumen_ruta)
        st.sidebar.metric("Distancia Total", f"{total_km:.2f} Km")

    # Dibujar marcadores
    for p in puntos_ruta:
        folium.Marker(
            location=[p['lat'], p['lon']],
            popup=f"<b>{p['nombre']}</b><br>Pozos: {p['pozos']}<br>E: {p['este']}<br>N: {p['norte']}",
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(m)

        # Etiqueta flotante con el número de orden
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(
                icon_size=(150,36),
                icon_anchor=(7,20),
                html=f'<div style="font-size: 10pt; color: white; background-color: #333; border-radius: 50%; width: 22px; height: 22px; display: flex; justify-content: center; align-items: center; border: 1px solid white;">{p["orden"]}</div>',
            )
        ).add_to(m)

    st_folium(m, width=1000, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Se presentó un error al procesar el archivo: {e}")
