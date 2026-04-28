import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon

# 1. Función de conversión DMS a Decimal (Robusta)
def dms_to_decimal(dms_str):
    try:
        if pd.isna(dms_str) or str(dms_str).strip() == "": return None
        if isinstance(dms_str, (int, float)): return float(dms_str)
        parts = re.findall(r"[-+]?\d*\.\d+|\d+", str(dms_str))
        if len(parts) == 1: return float(parts[0])
        if len(parts) < 3: return None
        deg, minu, sec = map(float, parts)
        decimal = deg + (minu / 60) + (sec / 3600)
        if any(char in str(dms_str).upper() for char in ['S', 'W', 'O']):
            decimal *= -1
        return decimal
    except:
        return None

# 2. Carga del archivo con Limpieza Profunda
@st.cache_data
def cargar_base_coordenadas(file_path):
    # Cargamos sin encabezado para identificar nosotros las filas
    df_raw = pd.read_csv(file_path, encoding='latin-1', header=None)
    
    # Buscamos la fila donde realmente empiezan los datos (ej. donde aparece RB-1 o RB-2)
    # Según tu imagen, los datos reales empiezan después de las filas de títulos
    start_row = 0
    for i, row in df_raw.iterrows():
        # Buscamos un patrón que indique el inicio de la tabla (ajusta según necesites)
        if "RB-" in str(row[0]) or "CASE" in str(row[0]):
            start_row = i
            break
            
    # Volvemos a leer desde la fila detectada, sin usar los nombres de columnas del CSV
    df = pd.read_csv(file_path, skiprows=start_row, encoding='latin-1', header=None)
    
    # ASIGNACIÓN POR POSICIÓN (Basado estrictamente en tu imagen):
    # Col 0: POZO | Col 2: Clúster | Col 5: Este Central | Col 6: Norte Central | Col 7: Lat | Col 8: Lon
    df_coords = df.iloc[:, [0, 2, 5, 6, 7, 8]].copy()
    df_coords.columns = ['pozo', 'cluster', 'este', 'norte', 'lat_raw', 'lon_raw']
    
    # Procesamiento de coordenadas
    df_coords['lat_dec'] = df_coords['lat_raw'].apply(dms_to_decimal)
    df_coords['lon_dec'] = df_coords['lon_raw'].apply(dms_to_decimal)
    
    # Agrupación por clúster para el mapa
    df_final = df_coords.dropna(subset=['lat_dec', 'lon_dec']).groupby('cluster').agg({
        'lat_dec': 'first', 
        'lon_dec': 'first', 
        'este': 'first',
        'norte': 'first',
        'pozo': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    return df_final

# --- INTERFAZ ---
st.title("🚜 Logística Rubiales & CASE - Etapa 2")

try:
    # Asegúrate de que el nombre del archivo sea idéntico al de tu repo
    df_maestro = cargar_base_coordenadas("COORDENADAS_RUB_CASE.csv")

    st.sidebar.header("Ruta de Movilización")
    ruta_input = st.sidebar.text_area("Pega los Clústeres (uno por línea):", placeholder="CASE-01\nRB-162")
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
                'este': match.iloc[0]['este']
            })

    # Mapa base centrado
    m = folium.Map(location=[df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()], zoom_start=11)

    # Marcadores y Orden
    for p in puntos_ruta:
        folium.Marker(
            location=[p['lat'], p['lon']],
            popup=f"Clúster: {p['nombre']}\nPozos: {p['pozos']}\nEste: {p['este']}",
            icon=folium.Icon(color='black', icon='oil-well', prefix='fa')
        ).add_to(m)

        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(
                icon_size=(150,36),
                icon_anchor=(7,20),
                html=f'<div style="font-size: 11pt; color: white; background-color: black; border-radius: 50%; width: 25px; height: 25px; display: flex; justify-content: center; align-items: center; border: 2px solid white; font-weight: bold;">{p["orden"]}</div>',
            )
        ).add_to(m)

    st_folium(m, width=1100, height=600)

except Exception as e:
    st.error(f"Error detectado: {e}")
    st.info("Sugerencia: Si el error persiste, revisa que el archivo CSV empiece directamente con los datos o que no tenga filas ocultas.")
