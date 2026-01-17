import streamlit as st
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from gedcom.element.individual import IndividualElement
from gedcom.parser import Parser
import re
import tempfile
import os
import numpy as np

# --- SIVUN ASETUKSET ---
st.set_page_config(page_title="Suku Kartalla", layout="wide")

st.title("📍 Sukututkimusdata Kartalla (Kertyvä)")

# --- APUFUNKTIOT ---

def get_year_from_date(date_str):
    if not date_str:
        return None
    match = re.search(r'\d{4}', date_str)
    return int(match.group(0)) if match else None

@st.cache_data
def parse_gedcom(file_content):
    # 1. Koodauksen korjaus
    decoded_text = ""
    try:
        decoded_text = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            decoded_text = file_content.decode('latin-1')
        except Exception:
            decoded_text = file_content.decode('utf-8', errors='ignore')

    # 2. Väliaikainen tiedosto
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ged", mode='w', encoding='utf-8') as tmp_file:
            tmp_file.write(decoded_text)
            tmp_path = tmp_file.name

        # 3. Jäsennys
        gedcom_parser = Parser()
        gedcom_parser.parse_file(tmp_path)
        
        root_child_elements = gedcom_parser.get_root_child_elements()
        data = []

        for element in root_child_elements:
            if isinstance(element, IndividualElement):
                try:
                    name_tuple = element.get_name()
                    first = name_tuple[0] if name_tuple[0] else ""
                    last = name_tuple[1] if name_tuple[1] else ""
                    full_name = f"{first} {last}".strip()

                    birth_data = element.get_birth_data()
                    
                    if birth_data and birth_data[1]: 
                        birth_date = birth_data[0]
                        birth_place = birth_data[1]
                        birth_year = get_year_from_date(birth_date)

                        if birth_year and birth_place:
                            data.append({
                                "Nimi": full_name,
                                "Syntymäaika": birth_date,
                                "Vuosi": birth_year,
                                "Paikka": birth_place
                            })
                except Exception:
                    continue
                    
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    
    return pd.DataFrame(data)

@st.cache_data
def geocode_dataframe(df):
    geolocator = Nominatim(user_agent="streamlit_family_map_optimized_v2")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1) 
    
    unique_places = df['Paikka'].unique()
    place_coords = {}
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total = len(unique_places)
    
    for i, place in enumerate(unique_places):
        progress = (i + 1) / total
        progress_bar.progress(progress)
        status_text.text(f"Haetaan koordinaatteja: {place} ({i+1}/{total})")
        
        if place not in place_coords:
            query = place
            if "finland" not in place.lower() and "suomi" not in place.lower():
                query = f"{place}, Finland"
                
            try:
                location = geocode(query)
                if location:
                    place_coords[place] = (location.latitude, location.longitude)
                else:
                    place_coords[place] = (None, None)
            except Exception:
                place_coords[place] = (None, None)
            
    status_text.empty()
    progress_bar.empty()
    
    df['lat'] = df['Paikka'].map(lambda x: place_coords.get(x, (None, None))[0])
    df['lon'] = df['Paikka'].map(lambda x: place_coords.get(x, (None, None))[1])
    
    return df.dropna(subset=['lat', 'lon'])

@st.cache_data
def create_cumulative_data(df, step=5):
    """
    OPTIMOITU VERSIO:
    Luo animaatiokehykset vain 'step' (oletus 5) vuoden välein.
    Tämä estää muistin loppumisen (AxiosError 404).
    """
    min_year = int(df['Vuosi'].min())
    max_year = int(df['Vuosi'].max())
    
    # Luodaan aikasarja 5 vuoden välein (esim. 1700, 1705, 1710...)
    years = range(min_year, max_year + step, step)
    
    cumulative_list = []
    
    for year in years:
        # Otetaan mukaan kaikki, jotka ovat syntyneet ennen tätä vuotta
        mask = df['Vuosi'] <= year
        # Otetaan vain tarvittavat sarakkeet kopioon muistin säästämiseksi
        step_data = df.loc[mask, ['Nimi', 'lat', 'lon', 'Vuosi', 'Syntymäaika', 'Paikka']].copy()
        
        if not step_data.empty:
            step_data['Animaatiovuosi'] = year
            cumulative_list.append(step_data)
    
    if not cumulative_list:
        return df
        
    return pd.concat(cumulative_list, ignore_index=True)

# --- KÄYTTÖLIITTYMÄ ---

uploaded_file = st.file_uploader("Lataa GEDCOM-tiedosto (.ged)", type=['ged'])

if uploaded_file is not None:
    bytes_data = uploaded_file.getvalue()
    df = parse_gedcom(bytes_data)
    
    if df.empty:
        st.error("Tiedostosta ei löytynyt sopivia tietoja.")
    else:
        st.success(f"Löydettiin {len(df)} henkilöä.")
        
        if st.button("Hae koordinaatit ja piirrä kartta"):
            with st.spinner('Haetaan sijaintitietoja...'):
                df_geo = geocode_dataframe(df)
            
            if df_geo.empty:
                st.warning("Koordinaatteja ei löytynyt.")
            else:
                st.info("Valmistellaan animaatiota (optimoidaan datamäärää)...")
                
                # Järjestys
                df_geo = df_geo.sort_values("Vuosi")
                
                # --- OPTIMOINTI ---
                # Jos dataa on paljon, kasvatetaan aikaväliä
                aikaväli = 5 
                if len(df_geo) > 500:
                    aikaväli = 10
                    st.warning("Suuri aineisto: Animaatio etenee 10 vuoden hyppäyksin suorituskyvyn takaamiseksi.")
                
                df_cumulative = create_cumulative_data(df_geo, step=aikaväli)
                
                st.success(f"Valmis! Piirretään {len(df_cumulative)} datapistettä.")
                
                # Piirrä kartta
                try:
                    fig = px.scatter_mapbox(
                        df_cumulative,
                        lat="lat",
                        lon="lon",
                        hover_name="Nimi",
                        hover_data={"Syntymäaika": True, "Paikka": True, "lat": False, "lon": False, "Vuosi": True, "Animaatiovuosi": False},
                        color_discrete_sequence=['blue'],
                        zoom=4.5,
                        center={"lat": 64.5, "lon": 26.0},
                        animation_frame="Animaatiovuosi",
                        title=f"Suvun leviäminen (n. {aikaväli} v välein)",
                        size_max=10
                    )

                    fig.update_layout(mapbox_style="open-street-map")
                    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
                    
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Karttaa ei voitu piirtää, aineisto on liian raskas selaimelle. ({e})")
