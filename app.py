import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon

# --- FUNCIONES DE SOPORTE ---

def dms_to_decimal(dms_str):
    """Convierte coordenadas de grados, minutos y segundos a decimal si es necesario"""
    try:
        if pd.isna(dms_str) or str(dms_str).strip() == "": return None
        # Si ya es un número decimal, lo devolvemos tal cual
        if isinstance(dms_str, (int, float)): return float(dms_str)
        
        parts = re.findall(r"[-+]?\d*\.\d+|\d+", str(dms_str))
        if len(parts) < 3: return float(parts[0]) if parts else None
        
        deg, minu, sec = map(float, parts)
        decimal = deg + (minu / 60) + (sec / 3600)
        if any(char in str(dms_str).upper() for char in ['S', 'W', 'O']):
            decimal *= -1
        return decimal
    except:
        return None

@st.cache_data
def cargar_base_coordenadas(file_path):
    # Saltamos las primeras 3 filas para limpiar el encabezado del Excel
    df = pd.read_csv(file_path, skiprows=3)
    
    # Seleccionamos las columnas por su posición exacta en tu nuevo archivo
    # 0:POZO, 2:CLUSTER, 5:ESTE_C, 6:NORTE_C, 7:LAT, 8:LON
    df_coords = df.iloc[:, [0, 2, 5, 6, 7, 8]].copy()
    df_coords.columns = ['pozo', 'cluster', 'este', 'norte', 'lat_raw', 'lon_raw']
    
    # Procesamos las coordenadas para el mapa (Folium requiere decimales)
    df_coords['lat_dec'] = df_coords['lat_raw'].apply(dms_to_decimal)
    df_coords['lon_dec'] = df_coords['lon_raw'].apply(dms_to_decimal)
    
    # Aseguramos que Este y Norte sean numéricos para cálculos de ingeniería
    df_coords['este'] = pd.to_numeric(df_coords['este'], errors='coerce')
    df_coords['norte'] = pd.to_numeric(df_coords['norte'], errors='coerce')
    
    # Agrupamos por clúster para que la búsqueda sea por ubicación, no por pozo individual
    df_final = df_coords.dropna(subset=['lat_dec', 'lon_dec']).groupby('cluster').agg({
        'lat_dec': 'first',
        'lon_dec': 'first',
        'este': 'first',
        'norte': 'first',
        'pozo': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    return df_final

# --- INTERFAZ DE STREAMLIT ---

st.title("🚜 Logística: Rubiales & Caño Sur Este (Etapa 2)")

try:
    # Carga del archivo con la nueva estructura
    df_maestro = cargar_base_coordenadas("COORDENADAS_RUB_CASE.csv")
    
    st.sidebar.header("Planificación de Ruta")
    ruta_input = st.sidebar.text_area("Lista de Clústeres (RB o CASE):", placeholder="CASE-01\nRB-1\nCASE-0096")
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
                'este': match.iloc[0]['este'],
                'norte': match.iloc[0]['norte'],
                'pozos': match.iloc[0]['pozo']
            })

    # Crear mapa centrado en el promedio de las coordenadas
    if not df_maestro.empty:
        m = folium.Map(location=[df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()], zoom_start=11)
        
        # Lógica de dibujo de ruta y marcadores (igual que tu versión 1)
        for p in puntos_ruta:
            # Marcador técnico con info de coordenadas planas
            folium.Marker(
                location=[p['lat'], p['lon']],
                popup=f"<b>({p['orden']}) {p['nombre']}</b><br>Pozos: {p['pozos']}<br>Este: {p['este']}<br>Norte: {p['norte']}",
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(m)
            
            # Etiqueta de orden
            folium.map.Marker(
                [p['lat'], p['lon']],
                icon=DivIcon(
                    icon_size=(150,36),
                    icon_anchor=(7,20),
                    html=f'<div style="font-size: 11pt; color: black; background-color: #f1c40f; border-radius: 50%; width: 22px; height: 22px; display: flex; justify-content: center; align-items: center; border: 1.5px solid black; font-weight: bold;">{p["orden"]}</div>',
                )
            ).add_to(m)

        st_folium(m, width=1000, height=500)
    
except Exception as e:
    st.error(f"Error al procesar el archivo: {e}")
